# -*- coding: utf-8 -*-
"""Tk-side scheduling for the isolated engine. Only completed values cross back."""
import keyboard_layout
import os
import pickle
import time
import traceback
import analysis_context
import shared_rows
import memory_usage
import analysis_work_app as input_work
from analysis_worker import Worker,WorkerExitedError,snapshot,state_key


# How often the prepare for the current text is looked for (2026-10-17: it
# was 25ms; every keystroke waits for this answer before its row is sent).
PREPARE_POLL_MS = 5


def _worker_fields(background,app=None):
    if background and not (app is not None and memory_usage.shares_worker(app)):
        return '_prefetch_worker', '_prefetch_worker_state', '_async_background_request'
    if background:
        # Mid (2026-10-15): the other tabs use the open tab's child while it is
        # idle, so only the request slot differs; the snapshot state is shared.
        return '_correction_worker', '_worker_state', '_async_background_request'
    return '_correction_worker', '_worker_state', '_async_request'


def _shared(background,worker_name):
    return background and worker_name=='_correction_worker'


def prewarm(app):
    """Start the existing foreground worker with public tables only, no snapshot.

    Main-thread stores can still be warming. The first real request supplies
    their completed state normally; this never reads user files. The editor's
    lines go along only to be parsed with the public dictionaries
    (Runtime.warm_lines).
    """
    if not memory_usage.prewarm(app) or getattr(app,'_closing',False) or getattr(app,'_correction_worker',None) is not None:
        return
    worker=None
    try:
        worker=Worker()
        # The open tab's lines, to parse with the public dictionaries after the
        # tables (Runtime.warm_lines, 2026-11-01): the first prepare reuses them.
        try:lines=app.editor.get('1.0','end-1c').split('\n')
        except Exception:lines=None
        worker.submit(dict(kind='warmup',lines=lines) if lines else dict(kind='warmup'))
        app._correction_worker=worker
        app._worker_state=None
    except Exception:
        if worker is not None:worker.close()
        traceback.print_exc()


def queue_idle_prewarm(app, delay=1200):
    """One optional retry after the document settles, never ahead of new input."""
    if not memory_usage.prewarm(app):
        memory_usage.queue_release(app, 'foreground')
        return
    if getattr(app, '_closing', False) or getattr(app, '_idle_prewarm_job', None) is not None:
        return
    worker = getattr(app, '_correction_worker', None)
    if worker is None or getattr(worker, '_idle_prewarm_submitted', False):
        return
    def start():
        app._idle_prewarm_job = None
        worker = getattr(app, '_correction_worker', None)
        if (not memory_usage.prewarm(app) or getattr(app, '_closing', False) or app._foreground_analysis_pending()
                or getattr(app, '_async_request', None) is not None
                or getattr(app, '_worker_state', None) is None
                or worker is None or not worker.process.is_alive()
                or getattr(worker, '_idle_prewarm_submitted', False)):
            return
        try:
            worker.submit(dict(kind='warmup'))
            worker._idle_prewarm_submitted = True
        except Exception:
            traceback.print_exc()
    app._idle_prewarm_job = app.root.after(delay, start)


def _request(app, task, scope, background=False, fields=None):
    if not background and fields is None:memory_usage.cancel_release(app, 'foreground')
    worker_name,state_name,request_name=fields or _worker_fields(background,app)
    if _shared(background,worker_name) and memory_usage.foreground_busy(app):
        # The open tab owns the one child (mid); a background request now
        # would supersede its work. The background step asks again when the
        # open tab is idle.
        return None
    worker=getattr(app,worker_name,None)
    if worker is not None and not worker.process.is_alive():
        worker.close();worker=None;setattr(app,state_name,None)
    if worker is None:
        worker=Worker();setattr(app,worker_name,worker)
    state=state_key(app)
    data=snapshot(app) if getattr(app,state_name,None)!=state else None
    if data is not None:data['_state_identity']=state
    identifier=worker.submit(task,data)
    setattr(app,state_name,state)
    setattr(app,request_name,(scope,identifier))
    if request_name=='_async_request':app._async_request_at=time.monotonic()
    elif request_name=='_async_background_request':app._async_background_request_at=time.monotonic()
    return identifier


def _cancel_request(app,background):
    """Stop only a request the UI has already decided not to consume."""
    worker_name,_,request_name=_worker_fields(background,app)
    pending=getattr(app,request_name,None)
    setattr(app,request_name,None)
    worker=getattr(app,worker_name,None)
    if pending is None or worker is None or getattr(worker,'closed',False) is True:return
    # A shared child (mid) runs only its newest request. A background request
    # that the open tab has already superseded must not be cancelled: the
    # cancel would interrupt the newer, foreground work instead.
    if _shared(background,worker_name) and pending[1]!=getattr(worker,'serial',pending[1]):return
    try:
        if worker.process.is_alive():worker.submit(dict(kind='cancel'))
    except Exception:
        # Failed cancellation must not block parking finished rows or closing.
        # The ordinary next request still checks/recreates a dead transport.
        traceback.print_exc()


def cancel_background_request(app):
    _cancel_request(app,True)


# Each edit of the open tab stops the walk over the other tabs. A row that is well under way in their own child
# is left to finish: stopped and asked again from the start each time, one long row in another tab was begun 7
# times (65 s of work thrown away) and never ended. Its answer waits for the walk to come back to it (same scope).
KEEP_BACKGROUND_ROW_S = 1.0
KEEP_BACKGROUND_ROW_MAX_S = 180.0


def _background_row_running(app):
    pending=getattr(app,'_async_background_request',None)
    if pending is None or pending[0][0]!='background' or _shared(True,_worker_fields(True,app)[0]):return False
    return KEEP_BACKGROUND_ROW_S<=time.monotonic()-getattr(app,'_async_background_request_at',0.0)<KEEP_BACKGROUND_ROW_MAX_S


def pause_background(app,on):
    """打った行を解いている間、裏のタブの子を待たせる（今打った分が最優先・うにさんの決めた順）。"""
    worker=getattr(app,'_prefetch_worker',None)
    flag=getattr(worker,'pause_flag',None)
    if flag is not None and bool(flag.value)!=bool(on):
        flag.value=1 if on else 0


def stop_background_request(app):
    pending=getattr(app,'_async_background_request',None)
    worker_name=_worker_fields(True,app)[0]
    if (pending is None or _shared(True,worker_name) or getattr(app,'_closing',False)
            or not _background_row_running(app)):
        _cancel_request(app,True)


def cancel_foreground_request(app):
    _cancel_request(app,False)


def _shown_light(app,i,line):
    # 手が止まった後の解き直し（重い段まで）: もう軽い答えが出ているので、途中の紫は要らない
    results=getattr(app,'line_results',None) or ()
    current=results[i] if 0<=i<len(results) else None
    return bool(current and current.get('original')==line and not current.get('pending'))


def _poll(app, scope, background=False):
    worker_name,_,request_name=_worker_fields(background,app)
    pending=getattr(app,request_name,None)
    if not pending or pending[0]!=scope:return False,None
    worker=getattr(app,worker_name,None)
    if worker is None:
        setattr(app,request_name,None);return False,None
    if _shared(background,worker_name) and pending[1]!=getattr(worker,'serial',pending[1]):
        # Superseded by the open tab's newer request on the one child (mid):
        # no answer will come for this id. Ask again when the child is idle.
        setattr(app,request_name,None);return False,None
    result=worker.poll(pending[1])
    if not background and scope[0]=='line' and not scope[5]:
        # 途中の紫（early_marks）: 答えの前は仮に塗り、答えが来たら外す（答えの紫で描き直す）
        import early_marks
        take=getattr(worker,'take_partial',None)
        parts=take(pending[1]) if take is not None else ()
        if not isinstance(parts,(list,tuple)):parts=()
        if result is not None:early_marks.clear_memo(app,scope[4])
        elif parts and not _shown_light(app,scope[4],parts[-1].get('line')):early_marks.memo(app,scope[4],parts[-1])
    if result is not None:
        setattr(app,request_name,None)
        if not background:memory_usage.queue_release(app, 'foreground')
    return True,result


def _error(app):
    app._analyze_error_reported=True
    app._analyze_last_error=traceback.format_exc()
    traceback.print_exc()
    try:app.status.config(text='解析でエラーが起きています（コンソール参照）')
    except Exception:pass



def _retry_foreground_exit(app,error):
    if not isinstance(error,WorkerExitedError):return False
    key=(input_work.token(app),state_key(app))
    if getattr(app,'_foreground_worker_retry',None)==key:return False
    # One transport retry for this input generation, across preparation/rows.
    # Completed rows stay valid; ordinary engine errors are never retried here.
    app._foreground_worker_retry=key
    app._async_request=None
    return True


def cached_context(app, text):
    return getattr(app,'_async_contexts',{}).get((state_key(app),text.rstrip('\n')))


def _save_context(app, text, value):
    cache=getattr(app,'_async_contexts',{})
    cache[(state_key(app),text.rstrip('\n'))]=value
    while len(cache)>memory_usage.context_cache_size(app):cache.pop(next(iter(cache)))
    app._async_contexts=cache


def context(app,text,lines):
    from literal_lines import literal_only,prepared
    literal=all(literal_only(line) for line in lines)
    if literal:cancel_foreground_request(app)
    import ime_speculation
    value=prepared(lines) if literal else cached_context(app,text)
    if value is None and not literal:
        # The row composed in the IME was sent ahead with this whole text
        # (take its answer first if it has come in the meantime).
        ime_speculation.waiting(app)
        value=ime_speculation.context_for(app,text)
        if value is not None:_save_context(app,text,value)
    if value is not None:
        app._async_context_scope=None
        _drop_packed(app,lines)
        app._startup_parsed=None
        app._startup_parse_tried=False
        app._attested_surfaces=value['attested']
        app._line_words_cache=dict(value['words'])
        return value
    scope=('prepare',input_work.token(app),state_key(app),text)
    if getattr(app,'_async_context_scope',None)==scope:return None
    _parse_pasted_lines(app,lines)
    if startup_parse_waiting(app):
        # The startup children are parsing this tab (start_startup_parse): ask once they answer
        _wait_for_startup_parse(app)
        try:app.status.config(text='解析の準備中…（編集できます）')
        except Exception:pass
        return None
    if ime_speculation.waiting(app):
        # A prepare now would supersede the composed row's request, whose
        # prepare answers this text when the commit matches. Look again soon.
        app.root.after(PREPARE_POLL_MS,app._analyze_if_changed)
        return None
    app._async_context_scope=scope
    try:
        task=dict(kind='prepare',lines=lines)
        # Sent with each prepare until one answers: a superseded one may not have reached the child
        parsed=getattr(app,'_startup_parsed',None)
        if parsed:task['parsed']=parsed
        packed=_packed_for(app,lines)
        if packed is not None:task['packed']=packed
        _request(app,task,scope)
        app.status.config(text='解析の準備中…（編集できます）')
    except Exception as error:
        app._async_context_scope=None
        if _retry_foreground_exit(app,error):app._analyze()
        else:_error(app)
        return None
    def complete():
        if (getattr(app,'_async_context_scope',None)!=scope or
                input_work.token(app)!=scope[1] or state_key(app)!=scope[2]):
            if getattr(app,'_async_context_scope',None)==scope:
                app._async_context_scope=None
                # Invalidation can happen without another key event. Discard
                # the stale value, then resume the current document's work.
                if not getattr(app,'_closing',False):app._analyze_if_changed()
            return
        try:
            present,value=_poll(app,scope)
            if not present:
                app._async_context_scope=None
                app._analyze()
                return
            if value is None:
                app.root.after(PREPARE_POLL_MS,complete);return
            _save_context(app,text,value)
            app._async_context_scope=None
            app._analyze()
        except Exception as error:
            app._async_context_scope=None
            if _retry_foreground_exit(app,error):app._analyze()
            else:_error(app)
    app.root.after(PREPARE_POLL_MS,complete)
    return None


def _tab_has_kana(text):
    # The file tab's whole text decides half-width -> full-width (2026-10-26・analysis_work.tab_has_kana)
    from analysis_work import tab_has_kana
    return tab_has_kana(text)


def _unit_values(app,result,value):
    key=(result['original'],result['corrected'])
    if not hasattr(app,'_units_cache'):app._units_cache={}
    if not hasattr(app,'_suspect_units_cache'):app._suspect_units_cache={}
    app._units_cache[key]=value['corrected_units']
    app._suspect_units_cache[key+(False,)]=value['original_units']
    app._suspect_units_cache[key+(True,)]=value['corrected_units']
    from boundary_colors import remember
    remember(app,value.get('navigation'))


def typed_rows(app):
    """打った文（確定した行）の列。打った順で、軽い答えと重い段のやり直しが済むまで残る（2026-11-07 うにさん「新しく
    書いた文は次々にキューを追加していくイメージ」）。"""
    order=getattr(app,'_typed_order',None)
    return order if isinstance(order,list) else []


def _typed_done(app,i):
    """最後の答えが出た打った行を列から外す（後の学習の解き直しなどは裏の扱い）。"""
    order=typed_rows(app)
    if i in order:order.remove(i)


def background_waits(app,i):
    """打った行ではない行（見えている範囲・下の先読み・学習の後の解き直し）を、今は子に頼まないか。

    打った行の列に済んでいない行がある間・変換中（入力途中の解析に当てる）・最後に打ってから待ち（NEIGHBOR_DEFER_MS・
    1.2秒）の間は頼まない（2026-11-07 うにさん「待ちの1.2秒というのは裏の文に取り掛かる待ち時間だけになる」）。"""
    if not getattr(app,'TYPED_QUEUE',False):return False
    order=typed_rows(app)
    if i in order:return False
    results=getattr(app,'line_results',None) or ()
    for row in order:
        r=results[row] if 0<=row<len(results) else None
        if r is None or r.get('pending') or r.get('deferred_stages'):
            app._typed_queue_busy_at=time.monotonic()
            return True
    try:
        import ime_watch
        if ime_watch.composition_live(app.editor.winfo_id()):return True
    except Exception:
        pass
    # 待つのは、列が空になってから（最後に列が埋まっていた時）と、最後に打ってから
    wait=getattr(app,'NEIGHBOR_DEFER_MS',0)/1000.0
    now=time.monotonic()
    for stamp in (getattr(app,'_typed_queue_busy_at',None),getattr(app,'_last_edit_at',None)):
        if stamp and now-stamp<wait:return True
    return False


def finish_typed_inflight(app):
    """子が今解いている打った行（打った行の列の行）を、新しい打鍵で打ち切らない（2026-11-07 うにさん「もしこの順序が
    入れ替わることで解きかけを捨てていたら、順序を守る」）。

    その行の字が変わっていなければ答えを待ち（'wait'）、届いたら今の段取りのままその行に入れる（'done'）。打った行で
    ない・その行を打ち直した・段取りが古い時は None（今までどおり新しい段取りが打ち切る）。"""
    if not getattr(app,'TYPED_QUEUE',False):return None
    pending=getattr(app,'_async_request',None)
    try:
        scope=pending[0]
    except (TypeError,IndexError):
        return None
    if not (isinstance(scope,tuple) and len(scope)>=6 and scope[0]=='line' and not scope[5]):return None
    i=scope[4]
    if i not in typed_rows(app):return None
    if scope[1]!=getattr(app,'_analyze_work',None) or scope[3]!=getattr(app,'_analyze_text',None):return None
    prev=getattr(app,'_prev_lines',None) or []
    if not 0<=i<len(prev):return None
    try:
        now=app.editor_source_text().split(chr(10))
    except Exception:
        return None
    head=0
    while head<len(now) and head<len(prev) and now[head]==prev[head]:head+=1
    tail=0
    while tail<len(now)-head and tail<len(prev)-head and now[len(now)-1-tail]==prev[len(prev)-1-tail]:tail+=1
    if not (i<head or i>=len(prev)-tail):return None       # その行そのものを打ち直した: 新しい段取りで
    try:
        present,value=_poll(app,scope)
    except Exception:
        return None
    if not present:return None
    if value is None:return 'wait'
    try:
        if value.get('prepared') is not None:
            prepared=value['prepared'];_save_context(app,app._analyze_text,prepared)
            app._analyze_ctx=prepared['context'];app._attested_surfaces=prepared['attested']
            app._line_words_cache=dict(prepared['words'])
        app.line_results[i]=analysis_context.completed(value)
        _unit_values(app,value['result'],value)
        if value['result'].get('deferred_stages'):
            arm=getattr(app,'_arm_heavy_redo',None)
            if arm is not None:arm()
        else:
            _typed_done(app,i)
    except Exception:
        return None
    return 'done'


def line_step(app,count):
    if plans_waiting(app):return    # a moment: the rows on screen get their sizes first
    if input_work.token(app)!=getattr(app,'_analyze_work',None):return
    if state_key(app)!=getattr(app,'_analyze_dependencies',None):
        app._analyze();return
    todo=app._analyze_todo
    for unused in range(count):
        pos=app._analyze_pos
        if pos>=len(todo):return
        i=todo[pos];lines=app._prev_lines
        if not 0<=i<min(len(lines),len(app.line_results)):
            app._analyze_pos+=1;continue
        res=app.line_results[i]
        # Restoring from the saved values builds only the display units; a row the saved values left
        # unfinished (a tab saved part-way, analysis_cache partial・2026-10-27) is corrected here in full
        from tab_analysis import reusable_result
        units_only=getattr(app,'_analyze_units_only',False) and reusable_result(res)
        from literal_lines import literal_only,result as literal_result,units as literal_units
        if literal_only(lines[i]):
            res=literal_result(lines[i])
            res['_context_evidence']=analysis_context.Reads({}).evidence()
            app.line_results[i]=res
            _unit_values(app,res,dict(corrected_units=literal_units(lines[i]),original_units=literal_units(lines[i])))
            app._analyze_pos+=1;continue
        key=(res['original'],res['corrected'])
        from boundary_colors import ready_for
        from pos_font import has_adjustments,current_colors
        navigation_enabled=((app.settings.get('show_ctrl_boundaries') or
                             has_adjustments(app.settings.get('pos_font_multipliers')) or
                             any(current_colors(app.settings).values())) and
                            getattr(getattr(app,'editor',None),'_correctnote_boundary_colors',None) is not None)
        navigation_ready=(not navigation_enabled or
                          ready_for(app,res['original'],res['corrected']))
        if (units_only and navigation_ready and key in getattr(app,'_units_cache',{})
                and key+(False,) in getattr(app,'_suspect_units_cache',{})):
            app._analyze_pos+=1;continue
        scope=('line',app._analyze_work,app._analyze_dependencies,app._analyze_text,i,units_only)
        if not units_only and getattr(app,'TYPED_QUEUE',False) and i in typed_rows(app):
            app._typed_queue_busy_at=time.monotonic()      # 列の行を解いている（裏はこの時から1.2秒待つ）
        if not units_only and helper_done(app,i):
            # The other child has this row (high・2026-10-30): finished, or still computing it; the pass waits
            # for that one before it ends (helper_busy)
            app._analyze_pos+=1;continue
        try:
            present,value=_poll(app,scope)
            if not present:
                if not units_only and background_waits(app,i):return   # 打った行の列が先（2026-11-07 うにさん）
                task=line_task(app,i,res,units_only)
                import ime_speculation
                value=None if units_only else ime_speculation.take(app,i,task)
                if value is None and not units_only:
                    # the same row with the same inputs is already finished elsewhere (shared_rows, 2026-11-08)
                    value=shared_rows.take_for(app,task,app._analyze_ctx,getattr(app,'_attested_surfaces',{}))
                if value is None:
                    if ime_speculation.waiting(app):return   # the composed row first
                    _request(app,task,scope)
                    return
            elif value is None:return
            # Recheck document identity at the point of application. A→B→A is
            # a different request even when its string happens to match.
            if app._analyze_work!=input_work.token(app) or app._analyze_dependencies!=state_key(app):return
            if value.get('prepared') is not None:
                prepared=value['prepared'];_save_context(app,app._analyze_text,prepared)
                app._analyze_ctx=prepared['context'];app._attested_surfaces=prepared['attested']
                app._line_words_cache=dict(prepared['words'])
            app.line_results[i]=analysis_context.completed(value)
            shared_rows.remember(app,app.line_results[i],value,app._analyze_ctx,app._analyze_dependencies)
            _unit_values(app,value['result'],value)
            reinput=getattr(app,'_reinput',None)
            if reinput is not None:reinput.on_answer(value['result'])
            if not value['result'].get('deferred_stages'):
                _typed_done(app,i)
            if value['result'].get('deferred_stages'):
                arm=getattr(app,'_arm_heavy_redo',None)
                if arm is not None:arm()
                # hands already still: this row's heavy redo is the next request, before the rows still to be read
                # (2026-11-07, the order 今打った分 → 見えている範囲: the next row went to the child first and the redo waited for it)
                now=getattr(app,'_heavy_redo_next',None)
                if now is not None:now(pos,i)
        except Exception as error:
            if _retry_foreground_exit(app,error):return
            _error(app)
            app._async_request=None
            res=dict(app._blank_result(lines[i]));res.pop('pending',None)
            res['analysis_error']=True;app.line_results[i]=res
            _unit_values(app,res,dict(corrected_units=(lines[i],[]),original_units=(lines[i],[])))
        app._analyze_pos+=1
        # The worker runs off Tk. Queue the next row now, then return on the
        # pending response so painting/input still get the whole event loop.


def defer_heavy(app,i):
    """The row being typed gets its answer without the heavy step (correction_entry defer_heavy); it is
    redone when the typing stops (app._flush_heavy_redo), and then this says no."""
    return (getattr(app,'NEIGHBOR_DEFER',False) is True
            and getattr(app,'_priority_input_row',None)==(input_work.token(app),i)
            and i not in getattr(app,'_heavy_redo',()))


def line_task(app,i,res,units_only):
    lines=app._prev_lines
    return dict(kind='units' if units_only else 'line',line=lines[i],result=res,
        context=app._analyze_ctx,input_method=(app.settings.get('input_method') or 'kana'),
        keyboard=keyboard_layout.spec(app.settings),
        nearby=() if units_only else app._nearby_words_for(i),
        lines=lines if units_only else None,
        recent=app.recent_words.words() if getattr(app,'recent_words',None) is not None else (),
        readings=input_work.line_readings(app,i,lines),calculations=input_work.line_calculations(app,i,lines),attested=getattr(app,'_attested_surfaces',{}),
        tab_has_kana=None if units_only else _tab_has_kana(getattr(app,'_analyze_text',None)),
        previous_line=None if units_only else analysis_context.previous_line_of(lines,i),
        defer_heavy=not units_only and defer_heavy(app,i))


def background_step(app,st):
    from tab_analysis import display_pending
    from literal_lines import literal_only,result as literal_result,units as literal_units
    st.setdefault('units',{});st.setdefault('suspect_units',{})
    if st['ctx'] is None and all(literal_only(line) for line in st['lines']):
        cancel_background_request(app)
        from literal_lines import prepared
        value=prepared(st['lines']);st['ctx']=value['context'];st['words']=value['words'];st['attested']=value['attested']
    if st['ctx'] is not None:
        while st['pos'] < len(st['lines']):
            i=st['pos']
            if i in st.get('skip',()) or not display_pending(st['results'][i],st['units'],st['suspect_units']):
                st['pos']+=1
            elif literal_only(st['lines'][i]):
                result=literal_result(st['lines'][i])
                result['_context_evidence']=analysis_context.Reads({}).evidence()
                st['results'][i]=result;st['pos']+=1
                key=(st['lines'][i],st['lines'][i])
                st['units'][key]=literal_units(st['lines'][i])
                st['suspect_units'][key+(False,)]=literal_units(st['lines'][i])
                st['suspect_units'][key+(True,)]=literal_units(st['lines'][i])
            else:
                break
        if st['pos']>=len(st['lines']):return
    units_only=st['ctx'] is not None and st['results'][st['pos']] is not None
    scope=('background',st['owner'],state_key(app),st['text'],st['pos'],st['ctx'] is None,units_only)
    present,value=_poll(app,scope,background=True)
    if not present:
        if st['ctx'] is None:
            value=cached_context(app,st['text'])
            if value is None:_request(app,dict(kind='prepare',lines=st['lines']),scope,background=True)
        else:
            i=st['pos']
            from context_vec import build_nearby_words
            words=st['words'];lines=st['lines']
            nearby=build_nearby_words(len(lines),i,lambda k:words.get(lines[k],[]) if 0<=k<len(lines) else [])
            task=dict(kind='units' if units_only else 'line',line=lines[i],result=st['results'][i],
                context=st['ctx'],input_method=(app.settings.get('input_method') or 'kana'),
                keyboard=keyboard_layout.spec(app.settings),
                nearby=nearby,attested=st['attested'],
                recent=app.recent_words.words() if getattr(app,'recent_words',None) is not None else (),
                readings=_background_readings(st,i),calculations=_background_readings(st,i,'calculations'),
                tab_has_kana=None if units_only else _tab_has_kana(st['text']),
                previous_line=None if units_only else analysis_context.previous_line_of(lines,i))
            # the same row with the same inputs is already finished elsewhere (shared_rows, 2026-11-08)
            value=None if units_only else shared_rows.take_for(app,task,st['ctx'],st['attested'])
            if value is None:_request(app,task,scope,background=True)
    if value is None:return
    if st['ctx'] is None:
        _save_context(app,st['text'],value)
        st['ctx']=value['context'];st['words']=value['words'];st['attested']=value['attested']
        from tab_analysis import rebase_background
        rebase_background(app,st)
        st.setdefault('units',{});st.setdefault('suspect_units',{})
    else:
        res=analysis_context.completed(value);st['results'][st['pos']]=res;st['pos']+=1
        if not units_only:shared_rows.remember(app,res,value,st['ctx'],scope[2])
        key=(res['original'],res['corrected'])
        st['units'][key]=value['corrected_units']
        st['suspect_units'][key+(False,)]=value['original_units']
        st['suspect_units'][key+(True,)]=value['corrected_units']
        from boundary_colors import remember
        remember(app,value.get('navigation'))


def close(app,keep_prewarmed=False):
    memory_usage.cancel_releases(app)
    _close_startup_parse(app,now=True)
    app._startup_parsed=None
    app._packed_rows=[]
    keep_prewarmed = keep_prewarmed and memory_usage.retains(app, 'foreground')
    job = getattr(app, '_idle_prewarm_job', None)
    if job is not None:
        app.root.after_cancel(job)
        app._idle_prewarm_job = None

    import quick_analysis
    quick_analysis.close(app)
    app._helper=None
    app._async_helper_request=None
    for worker_name,state_name,request_name in (_worker_fields(False),_worker_fields(True),_worker_fields(True,app)):
        worker=getattr(app,worker_name,None)
        if (keep_prewarmed and worker_name=='_correction_worker' and worker is not None
                and (getattr(app,request_name,None) or ((None,),))[0][0]=='plans' and worker.process.is_alive()):
            # Only the sizes of the rows on screen were asked (boundary_colors, before the first-run setup began):
            # that answer is let go (boundary_colors asks again or works them out) and the next request sends the
            # finished stores; the prewarmed child stays (2026-11-08: it was closed and started again)
            _cancel_request(app,False)
            setattr(app,state_name,None)
        # Initial dictionary import changes stores in the parent. A worker
        # with no snapshot or document request can finish its public-table
        # warmup safely and receive the completed stores afterwards.
        if (keep_prewarmed and worker_name=='_correction_worker' and worker is not None
                and getattr(app,state_name,None) is None
                and getattr(app,request_name,None) is None
                and worker.process.is_alive()):
            continue
        if worker is not None:worker.close()
        setattr(app,worker_name,None)
        setattr(app,state_name,None)
        setattr(app,request_name,None)


# ------------------------------------------------------------
# The reconversion list in the open tab's child (2026-11-02)
# ------------------------------------------------------------
# うにさん: the analysis's memory and the reconversion's must not be held at once. The child already holds
# the tables the list reads; the main process read them again on the first F5 (about 157MB, about 2.2 s, kept
# to the end of the run). The child's stores are the main process's (state_key), so the list is the same.
# A row in the child gives way (it is asked again by the next analysis step). With no child, or one busy
# with a prepare, the main process makes the list itself, as before.
CHILD_CANDIDATES = True
CHILD_CANDIDATES_WAIT_S = 8.0
CHILD_CANDIDATES_SPAWN = True


def child_alive(app):
    worker=getattr(app,'_correction_worker',None)
    try:
        return (worker is not None and not getattr(worker,'closed',False)
                and worker.process.is_alive())
    except Exception:
        return False


# The parsed rows of the open tab, packed (about 0.5 MB for 3,600 rows), kept by the window while no child runs
# (2026-11-03). Low gives its child back after 5 s idle, and the next key parsed the whole tab again: 6.8 s of 10.5 s
# on 3,600 rows. They read only the public dictionaries (Runtime.line_tokens). In memory only.
PACKED_ROWS_WAIT_S = 0.25
PACKED_ROWS_TABS = 2


def _same_tab(lines,kept):
    return len(lines&kept)*2>=len(lines)


def keep_rows(app,worker):
    """Before an idle child is closed. A slow answer is not waited for: the next child parses as before."""
    try:
        if not worker.process.is_alive():return
        identifier=worker.submit(dict(kind='packed_rows'))
        end=time.monotonic()+PACKED_ROWS_WAIT_S
        while time.monotonic()<end:
            value=worker.poll(identifier)
            if value is not None:
                kept=list(getattr(app,'_packed_rows',()))
                for lines,blob in value.get('tabs') or ():
                    kept=[item for item in kept if not _same_tab(lines,item[0])]+[(lines,blob)]
                app._packed_rows=kept[-PACKED_ROWS_TABS:]
                return
            time.sleep(.002)
    except Exception:
        traceback.print_exc()


def _packed_for(app,lines):
    if not getattr(app,'_packed_rows',()):return None
    current=frozenset(lines)
    for kept,blob in getattr(app,'_packed_rows',()):
        if _same_tab(current,kept):return blob
    return None


def _drop_packed(app,lines):
    held=getattr(app,'_packed_rows',None)
    if held:
        current=frozenset(lines)
        app._packed_rows=[item for item in held if not _same_tab(current,item[0])]


def plans_ask(app,texts):
    """Ask the open tab's child for the plans of rows on screen, without waiting (boundary_colors, 2026-11-03).

    A row in the child gives way and is asked again after the answer. Returns the scope for plans_poll, or None."""
    if not CHILD_CANDIDATES or not child_alive(app):return None
    pending=getattr(app,'_async_request',None)
    if pending is not None and pending[0][0]!='line':return None
    try:
        task=dict(kind='plans',texts=list(texts))
        if pending is not None:cancel_foreground_request(app)
        scope=('plans',time.monotonic())
        return scope if _request(app,task,scope) is not None else None
    except Exception:
        traceback.print_exc()
        return None


def plans_poll(app,scope):
    """(True, plans) answered; (True, None) still waiting; (False, None) nothing will come."""
    try:
        return _poll(app,scope)
    except Exception:
        traceback.print_exc()
        plans_cancel(app,scope)
        return False,None


def plans_cancel(app,scope):
    pending=getattr(app,'_async_request',None)
    if pending is not None and pending[0]==scope:cancel_foreground_request(app)


def plans_waiting(app):
    pending=getattr(app,'_async_request',None)
    return pending is not None and pending[0][0]=='plans'


def ask_child(app,task):
    """The answer of the open tab's child, or None: then the caller works it out itself."""
    if not CHILD_CANDIDATES:return None
    worker=getattr(app,'_correction_worker',None)
    if worker is None or getattr(worker,'closed',False):
        # The child was given back (mid, low: after a while idle). Without one the main process would read the
        # tables itself and keep them to the end of the run (about 150MB): start the child, it is given back again
        if not CHILD_CANDIDATES_SPAWN or getattr(app,'_closing',False):return None
        worker=None
    pending=getattr(app,'_async_request',None)
    if pending is not None and pending[0][0] not in ('line','prepare','plans'):return None
    preparing=pending is not None and pending[0][0]=='prepare'
    try:
        if worker is not None and not worker.process.is_alive():return None
        # What cannot cross to the child fails here: the queue's own thread would only drop it, unseen
        pickle.dumps(task,pickle.HIGHEST_PROTOCOL)
        if pending is not None:cancel_foreground_request(app)
        if preparing:
            # Asked again after this: the preparation is short, and reading the tables here is not
            app._async_context_scope=None
            root=getattr(app,'root',None)
            if root is not None:root.after(PREPARE_POLL_MS,app._analyze_if_changed)
        scope=('asked',time.monotonic())
        identifier=_request(app,task,scope)
        if identifier is None:return None
        worker=getattr(app,'_correction_worker',None)
        end=time.monotonic()+CHILD_CANDIDATES_WAIT_S
        while time.monotonic()<end:
            value=worker.poll(identifier)
            if value is not None:return value
            time.sleep(.002)
        cancel_foreground_request(app)
    except Exception:
        traceback.print_exc()
    finally:
        pending=getattr(app,'_async_request',None)
        if pending is not None and pending[0][0]=='asked':app._async_request=None
        memory_usage.queue_release(app,'foreground')
    return None


# ------------------------------------------------------------
# The open tab parsed by short-lived children at startup (2026-11-01)
# ------------------------------------------------------------
# The first prepare of a 3,600-line tab spent 2.9 s in janome after the English relearning answered, and
# the open tab's child is busy with its tables until then. Up to three more children, started with the
# warmup, each parse a part of the tab's lines with the public dictionaries only (Runtime.warm_lines) and
# close (about 3 s, about 140MB each). The first prepare takes their rows: the same rows it would make,
# so the answers are the same. うにさん 2026-11-01: use spare memory when there is some, at any memory
# setting, if the PC is not held up. So the number of children follows the free physical memory and the
# processors at startup; CN_STARTUP_PARSE=0 turns it off.
STARTUP_PARSE_ENABLED = os.environ.get('CN_STARTUP_PARSE') != '0'
STARTUP_PARSE_MIN_LINES = 400
# A file opened: the open tab's child is idle and warm, so the new children pay for their janome load
# (about 1.3 s) only on a long text (2026-11-02, the first prepare: 1,000 lines 1.62 -> 1.80 s, worse;
# 1,500 lines 2.31 -> 1.98 s; 2,000 lines 2.97 -> 2.23 s; 5,000 lines 6.9 -> 3.3 s). The same holds for a
# tab switched to (1,600 lines: later than without them), so a switch does not use them.
STARTUP_PARSE_OPEN_MIN_LINES = 2000
STARTUP_PARSE_CHILDREN = 3
# Each child: lines enough to pay for its janome load (about 1.3 s), memory, and two processors
STARTUP_PARSE_LINES_PER_CHILD = 300
STARTUP_PARSE_LINES_PER_PART = 1800   # about 1.3 + 3.6 s, inside the wait and STARTUP_PARSE_MAX_MS
STARTUP_PARSE_CHILD_MB = 160
STARTUP_PARSE_RESERVE_MB = 1500       # left free for Windows and the other applications
STARTUP_PARSE_CPUS_PER_CHILD = 2
STARTUP_PARSE_CPUS_KEPT = 4           # the app, its two children and the rest of the PC
# How long the first prepare waits for them, and how often it looks
STARTUP_PARSE_WAIT_S = 2.5
STARTUP_PARSE_POLL_MS = 30
# Closed by then whatever happens (a tab that never asks for a prepare, a slow PC)
STARTUP_PARSE_MAX_MS = 8000
# A finished child has ended by then, so its close does not wait
STARTUP_PARSE_CLOSE_MS = 1500


def _free_memory_mb():
    """Free physical memory now (Windows), or None."""
    try:
        import ctypes
        class Status(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),
                      ('available',ctypes.c_ulonglong),('page_total',ctypes.c_ulonglong),
                      ('page_available',ctypes.c_ulonglong),('virtual_total',ctypes.c_ulonglong),
                      ('virtual_available',ctypes.c_ulonglong),('extended',ctypes.c_ulonglong)]
        status=Status();status.length=ctypes.sizeof(Status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):return None
        return status.available//(1024*1024)
    except Exception:
        return None


def spare_memory_for(mb,free_mb=None):
    """Whether a short-lived child of `mb` leaves the reserve free (False when free memory is not known)."""
    if free_mb is None:free_mb=_free_memory_mb()
    return free_mb is not None and free_mb-STARTUP_PARSE_RESERVE_MB>=mb


def startup_parse_children(lines,cpus=None,free_mb=None):
    """How many startup children the PC has room for (0: none)."""
    cpus=(os.cpu_count() or 1) if cpus is None else cpus
    count=min(STARTUP_PARSE_CHILDREN,lines//STARTUP_PARSE_LINES_PER_CHILD,
              max(0,(cpus-STARTUP_PARSE_CPUS_KEPT)//STARTUP_PARSE_CPUS_PER_CHILD))
    if free_mb is None:free_mb=_free_memory_mb()
    if free_mb is None:return 0
    return max(0,min(count,(free_mb-STARTUP_PARSE_RESERVE_MB)//STARTUP_PARSE_CHILD_MB))


def start_startup_parse(app,own_share=False,min_lines=None,known=()):
    """At startup, and when a file is opened (2026-11-02: a 5,000-line file waited 6.9 s for its first
    prepare): the editor's text is the one the next prepare reads. own_share: the open tab's child is idle
    (a file was opened), so it parses a share too, while the new children load janome."""
    if getattr(app,'_startup_parse',None) is not None:_close_startup_parse(app)
    app._startup_parse=None;app._startup_parsed=None
    if not STARTUP_PARSE_ENABLED:return
    try:lines=app.editor.get('1.0','end-1c').split('\n')
    except Exception:return
    from literal_lines import literal_only
    todo=[line for line in dict.fromkeys(lines) if line.strip() and not literal_only(line) and line not in known]
    if len(todo)<(STARTUP_PARSE_MIN_LINES if min_lines is None else min_lines):return
    count=startup_parse_children(len(todo))
    if count<1:return
    own=getattr(app,'_correction_worker',None) if own_share else None
    if own is not None and (getattr(own,'closed',False) or getattr(app,'_async_request',None) is not None
                            or not own.process.is_alive()):own=None
    parts=count+(own is not None)
    # Short-lived: each takes what it parses in a few seconds; the prepare parses the rest of a very long text
    todo=todo[:STARTUP_PARSE_LINES_PER_PART*parts]
    jobs=[]
    try:
        for part in range(count):
            worker=Worker()
            jobs.append((worker,worker.submit(dict(kind='parse_lines',lines=todo[part::parts]))))
        # The open tab's child takes the last share (its warmup keeps the rows; the prepare interrupts it)
        if own is not None:own.submit(dict(kind='warmup',lines=todo[count::parts]))
    except Exception:
        for worker,_job in jobs:worker.close()
        traceback.print_exc();return
    # The children load janome first (about 1.3 s), then about 2 ms a line
    wait=max(STARTUP_PARSE_WAIT_S,1.5+0.0025*len(todo)/parts)
    app._startup_parse=dict(jobs=jobs,results=[None]*len(jobs),since=None,wait=wait)
    app._startup_parse_tried=True
    state=app._startup_parse
    def expire():
        if getattr(app,'_startup_parse',None) is state:_close_startup_parse(app)
    try:app.root.after(STARTUP_PARSE_MAX_MS,expire)
    except Exception:pass


def _parse_pasted_lines(app,lines):
    """An edit added many lines to the open tab (a paste: 5,000 lines waited 7.2 s for the prepare): the same
    children parse the new lines, once until that prepare answers. Not on a tab switch: see the limit above."""
    prev=getattr(app,'_prev_lines',None)
    if (not prev or len(lines)-len(prev)<STARTUP_PARSE_OPEN_MIN_LINES or getattr(app,'_startup_parse_tried',False)
            or getattr(app,'_startup_parse',None) is not None):return
    work=getattr(app,'_analyze_work',None)
    if not work or work[0]!=input_work.token(app)[0]:return
    try:start_startup_parse(app,own_share=True,min_lines=STARTUP_PARSE_OPEN_MIN_LINES,known=frozenset(prev))
    except Exception:traceback.print_exc()


def _close_startup_parse(app,now=False):
    state=getattr(app,'_startup_parse',None)
    app._startup_parse=None
    job=getattr(app,'_startup_parse_poll',None)
    app._startup_parse_poll=None
    if job is not None:
        try:app.root.after_cancel(job)
        except Exception:pass
    for worker,_job in (state or {}).get('jobs',()):
        # Ask the child to end now and close it once it has: closing at once waited for each process on
        # the window's thread (0.21 s for three, 2026-11-01)
        try:worker.inbox.put_nowait(None)
        except Exception:pass
        try:
            if now:raise RuntimeError('closing now')
            app.root.after(STARTUP_PARSE_CLOSE_MS,worker.close)
        except Exception:
            try:worker.close()
            except Exception:pass


def startup_parse_waiting(app):
    """Whether the first prepare waits for the startup parse (asked when it is about to be sent, after the
    rows the saved analysis has are shown). When every part has come, its rows go to app._startup_parsed."""
    state=getattr(app,'_startup_parse',None)
    if state is None:return False
    if state['since'] is None:state['since']=time.monotonic()
    try:
        for part,(worker,job) in enumerate(state['jobs']):
            if state['results'][part] is None:state['results'][part]=worker.poll(job)
    except Exception:
        traceback.print_exc();_close_startup_parse(app);return False
    if all(result is not None for result in state['results']):
        _close_startup_parse(app)
        app._startup_parsed=dict(blobs=[result['blob'] for result in state['results']])
        return False
    if getattr(app,'_closing',False) or time.monotonic()-state['since']>state.get('wait',STARTUP_PARSE_WAIT_S):
        _close_startup_parse(app);return False
    return True


def _wait_for_startup_parse(app):
    """Look again for the startup parse until it answers or is given up, then analyse (once)."""
    if getattr(app,'_startup_parse_poll',None) is not None:return
    def check():
        app._startup_parse_poll=None
        if getattr(app,'_closing',False):return
        if startup_parse_waiting(app):
            app._startup_parse_poll=app.root.after(STARTUP_PARSE_POLL_MS,check);return
        app._analyze()
    app._startup_parse_poll=app.root.after(STARTUP_PARSE_POLL_MS,check)


# ------------------------------------------------------------
# The second child helps the open tab (high・2026-10-30 うにさん「子2つで分けて」)
# ------------------------------------------------------------
# Order of importance (うにさん): the row just typed, then the rows in view, then the rows below in the same
# tab, then the other tabs ("ある程度遅くなっても構わない"). The open tab's child takes its rows in that order;
# the other tabs' child takes the next row after it in the same order, so the two leapfrog down the list and
# the open tab's child skips the rows the helper has finished. The other tabs wait while the helper has work.
# Not while typing, and not for a short pass (the load matters as much as the speed); results are the same as
# one child's (each row is corrected from the same inputs).
HELPER_MIN_ROWS = 8
HELPER_SCAN = 200
HELPER_FIELDS = ('_prefetch_worker', '_prefetch_worker_state', '_async_helper_request')


def _helper_key(app):
    return (getattr(app, '_analyze_work', None), getattr(app, '_analyze_dependencies', None),
            getattr(app, '_analyze_text', None))


def _helper_state(app):
    key = _helper_key(app)
    st = getattr(app, '_helper', None)
    if st is None or st['key'] != key:
        if st is not None and st.get('row') is not None:
            _helper_cancel(app)
        st = app._helper = dict(key=key, row=None, done=set())
    return st


def _helper_cancel(app):
    pending = getattr(app, '_async_helper_request', None)
    app._async_helper_request = None
    worker = getattr(app, '_prefetch_worker', None)
    if pending is None or worker is None or getattr(worker, 'closed', False) is True:
        return
    try:
        if worker.process.is_alive():
            worker.submit(dict(kind='cancel'))
    except Exception:
        traceback.print_exc()


def helper_allowed(app):
    """The helper may take a row of the open tab now."""
    if _background_row_running(app):return False   # 同じ子で裏のタブの長い行を計算中: 済むまで待つ（打ち切ると最初からになる）
    if not memory_usage.prefetch_worker(app) or getattr(app, '_closing', False):
        return False
    if getattr(app, '_analyze_units_only', False) or getattr(app, '_analyze_ctx', None) is None:
        return False
    if input_work.token(app) != getattr(app, '_analyze_work', None):
        return False
    if state_key(app) != getattr(app, '_analyze_dependencies', None):
        return False
    interacting = getattr(app, '_interacting', None)
    if callable(interacting) and interacting():
        return False
    todo = getattr(app, '_analyze_todo', ()) or ()
    return len(todo) - getattr(app, '_analyze_pos', 0) >= HELPER_MIN_ROWS


def helper_busy(app):
    """A row of the open tab is with the helper (the open tab's pass waits for it before it ends)."""
    st = getattr(app, '_helper', None)
    return st is not None and st.get('row') is not None and st['key'] == _helper_key(app)


def helper_done(app, index):
    """The helper has finished (or is computing) this row of the current pass."""
    st = getattr(app, '_helper', None)
    if st is None or st['key'] != _helper_key(app):
        return False
    if index == st.get('row'):
        return True
    # A row made pending again since (a new context with the same key) is not finished: passing over it ended
    # the pass with the row unanalysed and nothing scheduled
    if index not in st['done']:
        return False
    results = getattr(app, 'line_results', ())
    from tab_analysis import reusable_result
    return 0 <= index < len(results) and reusable_result(results[index])


def helper_wanted(app):
    """The other tabs wait: the open tab still has rows for the helper."""
    return helper_busy(app) or helper_allowed(app)


def helper_step(app):
    """Collect the helper's row and give it the next one. Returns the row that came in, or None."""
    st = _helper_state(app)
    landed = None
    if st['row'] is not None:
        scope = ('helper',) + st['key'] + (st['row'],)
        pending = getattr(app, '_async_helper_request', None)
        worker = getattr(app, '_prefetch_worker', None)
        if not pending or pending[0] != scope or worker is None:
            st['row'] = None
        else:
            try:
                value = worker.poll(pending[1])
            except Exception:
                traceback.print_exc()
                app._async_helper_request = None
                st['row'] = None
                return None
            if value is None:
                return None
            app._async_helper_request = None
            i = st['row']
            st['row'] = None
            lines = getattr(app, '_prev_lines', [])
            if (0 <= i < min(len(lines), len(app.line_results))
                    and value['result'].get('original') == lines[i]):
                app.line_results[i] = analysis_context.completed(value)
                _unit_values(app, value['result'], value)
                st['done'].add(i)
                landed = i
    if st['row'] is not None or not helper_allowed(app):
        return landed
    from literal_lines import literal_only
    todo = app._analyze_todo
    pos = app._analyze_pos
    lines = app._prev_lines
    for i in todo[pos + 1:pos + 1 + HELPER_SCAN]:
        if i in st['done'] or not 0 <= i < min(len(lines), len(app.line_results)) or literal_only(lines[i]):
            continue
        task = line_task(app, i, app.line_results[i], False)
        scope = ('helper',) + st['key'] + (i,)
        try:
            app._async_background_request = None       # the other tabs ask again when the helper is free
            _request(app, task, scope, fields=HELPER_FIELDS)
            st['row'] = i
        except Exception:
            traceback.print_exc()
        break
    return landed


def _background_readings(state,index,attribute='readings'):
    from analysis_work import Document
    readings=tuple(state.get(attribute,()))
    if not readings:return ()
    document=state.get('_reading_document')
    if document is None or document.text!=state['text']:
        document=Document(state['owner'],state['text']);state['_reading_document']=document
    if attribute=='calculations':
        document.calculations=readings
        return document.row_calculations(index,state['lines'][index])
    document.occurrences=readings
    return document.row_readings(index,state['lines'][index])
