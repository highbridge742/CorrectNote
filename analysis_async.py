# -*- coding: utf-8 -*-
"""Tk-side scheduling for the isolated engine. Only completed values cross back."""
import traceback
import analysis_context
import analysis_work_app as input_work
from analysis_worker import Worker,WorkerExitedError,snapshot,state_key


def _worker_fields(background):
    if background:
        return '_prefetch_worker', '_prefetch_worker_state', '_async_background_request'
    return '_correction_worker', '_worker_state', '_async_request'


def _request(app, task, scope, background=False):
    worker_name,state_name,request_name=_worker_fields(background)
    worker=getattr(app,worker_name,None)
    if worker is not None and not worker.process.is_alive():
        worker.close();worker=None;setattr(app,state_name,None)
    if worker is None:
        worker=Worker();setattr(app,worker_name,worker)
    state=state_key(app)
    data=snapshot(app) if getattr(app,state_name,None)!=state else None
    identifier=worker.submit(task,data)
    setattr(app,state_name,state)
    setattr(app,request_name,(scope,identifier))
    return identifier


def _poll(app, scope, background=False):
    worker_name,_,request_name=_worker_fields(background)
    pending=getattr(app,request_name,None)
    if not pending or pending[0]!=scope:return False,None
    result=getattr(app,worker_name).poll(pending[1])
    if result is not None:setattr(app,request_name,None)
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
    while len(cache)>4:cache.pop(next(iter(cache)))
    app._async_contexts=cache


def context(app,text,lines):
    value=cached_context(app,text)
    if value is not None:
        app._async_context_scope=None
        app._attested_surfaces=value['attested']
        app._line_words_cache=dict(value['words'])
        return value
    scope=('prepare',input_work.token(app),state_key(app),text)
    if getattr(app,'_async_context_scope',None)==scope:return None
    app._async_context_scope=scope
    try:
        _request(app,dict(kind='prepare',lines=lines),scope)
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
                app.root.after(25,complete);return
            _save_context(app,text,value)
            app._async_context_scope=None
            app._analyze()
        except Exception as error:
            app._async_context_scope=None
            if _retry_foreground_exit(app,error):app._analyze()
            else:_error(app)
    app.root.after(25,complete)
    return None


def _unit_values(app,result,value):
    key=(result['original'],result['corrected'])
    if not hasattr(app,'_units_cache'):app._units_cache={}
    if not hasattr(app,'_suspect_units_cache'):app._suspect_units_cache={}
    app._units_cache[key]=value['corrected_units']
    app._suspect_units_cache[key+(False,)]=value['original_units']
    app._suspect_units_cache[key+(True,)]=value['corrected_units']


def line_step(app,count):
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
        units_only=getattr(app,'_analyze_units_only',False)
        res=app.line_results[i]
        if lines[i]=='':
            res=dict(app._blank_result(''));res.pop('pending',None)
            res['_context_evidence']=analysis_context.Reads({}).evidence()
            app.line_results[i]=res
            _unit_values(app,res,dict(corrected_units=('',[]),original_units=('',[])))
            app._analyze_pos+=1;continue
        key=(res['original'],res['corrected'])
        if units_only and key in getattr(app,'_units_cache',{}) and key+(False,) in getattr(app,'_suspect_units_cache',{}):
            app._analyze_pos+=1;continue
        scope=('line',app._analyze_work,app._analyze_dependencies,app._analyze_text,i,units_only)
        try:
            present,value=_poll(app,scope)
            if not present:
                task=dict(kind='units' if units_only else 'line',line=lines[i],result=res,
                    context=app._analyze_ctx,input_method=(app.settings.get('input_method') or 'kana'),
                    nearby=() if units_only else app._nearby_words_for(i),
                    lines=lines if units_only else None,
                    recent=app.recent_words.words() if getattr(app,'recent_words',None) is not None else (),
                    readings=input_work.line_readings(app,i,lines),calculations=input_work.line_calculations(app,i,lines),attested=getattr(app,'_attested_surfaces',{}))
                _request(app,task,scope)
                return
            if value is None:return
            # Recheck document identity at the point of application. A→B→A is
            # a different request even when its string happens to match.
            if app._analyze_work!=input_work.token(app) or app._analyze_dependencies!=state_key(app):return
            if value.get('prepared') is not None:
                prepared=value['prepared'];_save_context(app,app._analyze_text,prepared)
                app._analyze_ctx=prepared['context'];app._attested_surfaces=prepared['attested']
                app._line_words_cache=dict(prepared['words'])
            app.line_results[i]=analysis_context.completed(value)
            _unit_values(app,value['result'],value)
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


def background_step(app,st):
    from tab_analysis import display_pending
    st.setdefault('units',{});st.setdefault('suspect_units',{})
    if st['ctx'] is not None:
        while st['pos'] < len(st['lines']):
            i=st['pos']
            if not display_pending(st['results'][i],st['units'],st['suspect_units']):
                st['pos']+=1
            elif st['lines'][i]=='':
                result=dict(app._blank_result(''));result.pop('pending',None)
                result['_context_evidence']=analysis_context.Reads({}).evidence()
                st['results'][i]=result;st['pos']+=1
            else:
                break
        if st['pos']>=len(st['lines']):return
    units_only=st['ctx'] is not None and st['results'][st['pos']] is not None
    scope=('background',st['owner'],st['work_epoch'],state_key(app),st['text'],st['pos'],st['ctx'] is None,units_only)
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
            _request(app,dict(kind='units' if units_only else 'line',line=lines[i],result=st['results'][i],
                context=st['ctx'],input_method=(app.settings.get('input_method') or 'kana'),
                nearby=nearby,attested=st['attested'],
                recent=app.recent_words.words() if getattr(app,'recent_words',None) is not None else (),
                readings=_background_readings(st,i),calculations=_background_readings(st,i,'calculations')),scope,background=True)
    if value is None:return
    if st['ctx'] is None:
        _save_context(app,st['text'],value)
        st['ctx']=value['context'];st['words']=value['words'];st['attested']=value['attested']
        from tab_analysis import rebase_background
        rebase_background(app,st)
        st.setdefault('units',{});st.setdefault('suspect_units',{})
    else:
        res=analysis_context.completed(value);st['results'][st['pos']]=res;st['pos']+=1
        key=(res['original'],res['corrected'])
        st['units'][key]=value['corrected_units']
        st['suspect_units'][key+(False,)]=value['original_units']
        st['suspect_units'][key+(True,)]=value['corrected_units']


def close(app):
    import quick_analysis
    quick_analysis.close(app)
    for worker_name,state_name,request_name in (_worker_fields(False),_worker_fields(True)):
        worker=getattr(app,worker_name,None)
        if worker is not None:worker.close()
        setattr(app,worker_name,None)
        setattr(app,state_name,None)
        setattr(app,request_name,None)


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
