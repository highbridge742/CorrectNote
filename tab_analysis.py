# -*- coding: utf-8 -*-
"""Volatile completed values for currently open documents, including IME ranges.

No history is written. Shared text-only disk caches remain a separate concern.
"""
from analysis_worker import state_key,same_model_state,result_compatible,model_moved,choices_moved
from analysis_cache import keep_answer,kept_answer,reusable_result
import analysis_work_app as work


def _readings(app, owner):
    doc=getattr(app,'_input_documents',{}).get(owner)
    if doc is None and owner==work.owner(app):doc=getattr(app,'_input_document',None)
    return tuple(doc.occurrences) if doc is not None else ()


def _calculations(app, owner):
    doc=getattr(app,'_input_documents',{}).get(owner)
    if doc is None and owner==work.owner(app):doc=getattr(app,'_input_document',None)
    return tuple(doc.calculations) if doc is not None else ()


def learned_since(app,previous,current=None):
    """previous, with the revision that only automatic learning moved since then set to the current one.

    Learning a word bumps _analysis_state_revision (state_key element 3) so that other tabs' saved values are no
    longer taken as they stand. Each row can still say whether it used the learned word (used_keys), as the open tab's
    rows already do (_learning_baseline・2026-11-07). Without this every other tab was read again from the first row
    after each automatic learning, with the same answers (2026-11-07: 55 of 80 rows in 150 idle seconds).
    Any other bump on the way (input method, dictionary, an explicit choice) leaves previous as it is."""
    if previous is None:return previous
    try:
        current=state_key(app) if current is None else current
        if len(previous)!=len(current) or previous[3]==current[3]:return previous
        steps=getattr(app,'_learning_revisions',None) or {}
        revision=current[3]
        while revision!=previous[3]:
            if revision not in steps:return previous
            revision=steps[revision]
        return tuple(previous[:3])+(current[3],)+tuple(previous[4:])
    except Exception:
        return previous


def prefetch_order(app):
    """Next tab, previous active tab, then the remaining circular order."""
    tabs=app.session.tabs;n=len(tabs)
    if n<2:return []
    current=max(0,min(app.session.active,n-1))
    order=[(current+step)%n for step in range(1,n)]
    previous=getattr(app,'_prev_active',None)
    if previous in order and previous!=order[0]:
        order.remove(previous);order.insert(1,previous)
    return order


def _registry(app):
    live={work.owner_for_tab(app,tab) for tab in app.session.tabs}
    cache=getattr(app,'_completed_tabs',{})
    for owner in list(cache):
        if owner not in live:cache.pop(owner,None)
    app._completed_tabs=cache
    return cache


def forget_closed(app):
    """Release owner-specific work as soon as its tab closes."""
    live={work.owner_for_tab(app,tab) for tab in app.session.tabs}
    for name in ('_completed_tabs','_fg_parked','_bg_parked','_input_documents'):
        cache=getattr(app,name,None)
        if cache is not None:
            for owner in list(cache):
                if owner not in live:cache.pop(owner,None)


def completed(app,text,owner=None):
    owner=work.owner(app) if owner is None else owner
    saved=_registry(app).get(owner)
    if (saved and saved['text']==text.rstrip('\n')
            and saved['readings']==_readings(app,owner)
            and saved.get('calculations',())==_calculations(app,owner)):
        current=state_key(app);previous=learned_since(app,saved['dependencies'],current)
        if previous==current:return saved
        if same_model_state(previous,current):
            if model_moved(previous,current):
                # The vocabulary or the choice memory moved (2026-10-24): the saved context was built from the
                # old store. Keep this baseline; the background step prepares the context again and keeps the
                # rows that did not use what moved (background_values → rebase_background)
                return None
            results=[r if result_compatible(app,r,previous,current) else None for r in saved['results']]
            if all(r is not None for r in results):
                saved['dependencies']=current
                return saved
            # Preserve the valid portion for foreground entry or background
            # resumption; a new IME pair is not a reason to lose a whole tab.
            prepared=saved['prepared']
            park_background(app,dict(owner=owner,text=saved['text'],lines=saved['text'].split('\n'),
                results=results,dependencies=current,readings=saved['readings'],
                calculations=saved.get('calculations',()),ctx=prepared['context'],
                words=prepared['words'],attested=prepared['attested'],
                units=saved['units'],suspect_units=saved['suspect'],work_epoch=getattr(app,'_work_epoch',0)))
            _registry(app).pop(owner,None)
    return None


def _save(app,owner,text,results,prepared,units,suspect,dependencies,readings,calculations=()):
    if dependencies!=state_key(app):return False
    key=text.rstrip('\n')
    count=len(key.split('\n'))
    core=results[:count]
    if (not key or len(core)!=count or any(not reusable_result(r) for r in core)
            or any(r['original']!=line for r,line in zip(core,key.split('\n')))):
        return False
    pairs={(r['original'],r['corrected']) for r in core}
    cache=_registry(app);cache.pop(owner,None)
    cache[owner]=dict(text=key,results=list(core),prepared=prepared,dependencies=dependencies,
        readings=tuple(readings),calculations=tuple(calculations),units={k:v for k,v in units.items() if k in pairs},
        suspect={k:v for k,v in suspect.items() if k[:2] in pairs})
    # This cache has one entry per open tab. _registry drops closed tabs;
    # evicting a live owner makes an unchanged tab run correction again.
    # Memory usage low (2026-10-15) keeps only the open tab's entry: the
    # other tabs run correction again when visited (same answers, slower;
    # about 40MB for five other long tabs in the main process).
    import memory_usage
    limit=memory_usage.completed_tabs(app)
    if limit is not None:
        for other in [name for name in cache if name!=owner][:max(0,len(cache)-limit)]:
            cache.pop(other,None)
    return True


def remember(app):
    if (getattr(app,'_analyze_work',None)!=work.token(app)
            or getattr(app,'_analyze_pos',0)<len(getattr(app,'_analyze_todo',()))):return False
    owner=work.owner(app)
    readings=tuple(getattr(app,'_analyze_readings',()))
    calculations=tuple(getattr(app,'_analyze_calculations',()))
    if readings!=_readings(app,owner) or calculations!=_calculations(app,owner):return False
    prepared=dict(context=getattr(app,'_analyze_ctx',{}),attested=getattr(app,'_attested_surfaces',{}),
                  words=dict(getattr(app,'_line_words_cache',{})))
    return _save(app,owner,app._analyze_text,app.line_results,prepared,
        getattr(app,'_units_cache',{}),getattr(app,'_suspect_units_cache',{}),
        getattr(app,'_analyze_dependencies',None),readings,calculations)


def display_pending(result,units,suspect):
    """A reusable correction can still lack either pane's display values."""
    if not reusable_result(result):return True
    if not result['original']:return False
    key=(result['original'],result['corrected'])
    return key not in units or key+(False,) not in suspect


def display_ready(saved):
    return bool(saved) and not any(display_pending(r,saved['units'],saved['suspect'])
                                   for r in saved['results'])


def restored_without_proof(result):
    """A finished row read back from the saved file: it has an answer but no record of what it used (used_keys, up to
    480 KB a row, is not saved). Whether a change touches it is unknown, but its answer is still the best there is."""
    return (isinstance(result,dict) and bool(result.get('original')) and bool(result.get('_from_file'))
            and 'used_keys' not in result and '_context_evidence' not in result
            and (reusable_result(result) or kept_answer(result)))


def previous_values(app,owner):
    """One owner's last analysis is a baseline, not a completed current value."""
    value=getattr(app,'_fg_parked',{}).get(owner)
    if value is not None:return _learned_view(app,value)
    saved=_registry(app).get(owner)
    if saved is None:
        # Part of the tab read in the background. When the vocabulary has moved (each finished tab's learning does)
        # background_compatible turns it down as it stands, and its rows were all read again from the first row
        # (2026-11-05 うにさん「次のタブを開くと、解析が1行目から始まることが時々ある」): each row is checked by itself below
        parked=getattr(app,'_bg_parked',{}).get(owner)
        if not parked or parked.get('ctx') is None:return None
        return dict(parked,suspect=parked.get('suspect_units',{}),dependencies=learned_since(app,parked.get('dependencies')),
                    prepared=dict(context=parked['ctx'],attested=parked.get('attested',{}),words=parked.get('words',{})))
    return dict(saved,lines=saved['text'].split('\n'),ctx=saved['prepared']['context'],
                dependencies=learned_since(app,saved.get('dependencies')))


def _learned_view(app,value):
    previous=value.get('dependencies')
    current=learned_since(app,previous)
    return value if current==previous else dict(value,dependencies=current)


def restore_previous(app,text,lines):
    """Restore the old inputs too, so the ordinary differential plan validates them."""
    owner=work.owner(app);base=previous_values(app,owner);open_rows=base
    parked=getattr(app,'_bg_parked',{}).get(owner)
    if parked and not background_compatible(app,parked):parked=None
    if parked and parked.get('ctx') is not None:
        base=dict(parked,suspect=parked.get('suspect_units',{}),
            prepared=dict(context=parked['ctx'],attested=parked.get('attested',{}),
                          words=parked.get('words',{})))
        # The part read in the background, seen through learned_since as every other baseline here is
        # (previous_values): when only automatic learning had moved since the tab was left, its old key was taken
        # as it stood, failed same_model_state below, and the whole tab was read again from the first row
        # (2026-11-08 うにさん「タブ移動したら全体的に未解析印が付きました」). CN_LEARNED_PARKED=0: the old form
        import os
        if os.environ.get('CN_LEARNED_PARKED')!='0':
            base['dependencies']=learned_since(app,parked.get('dependencies'))
    dependencies=state_key(app)
    if (not base or not same_model_state(base.get('dependencies'),dependencies)
            or not base.get('lines') or len(base['results'])!=len(base['lines'])):return
    old_lines=list(base['lines'])
    # The parked copy holds finished rows only: a row with an answer still to be finished is in the rows as they were left
    waiting={}
    if open_rows and open_rows is not base and open_rows.get('dependencies')==base['dependencies']:
        waiting={i:row for i,row in enumerate(open_rows['results']) if row and row.get('deferred_stages')}
    results=[]
    for i,(r,line) in enumerate(zip(base['results'],old_lines)):
        r=r or waiting.get(i)
        if (r or {}).get('original')!=line:results.append(app._blank_result(line))
        elif restored_without_proof(r) and (kept_answer(r) or not result_compatible(app,r,base['dependencies'],dependencies)):
            # Went away from this tab with rows read back from the saved file, and a word moved: they keep their answers
            results.append(keep_answer(r));getattr(app,'_arm_heavy_redo',lambda:None)()
        elif reusable_result(r) and result_compatible(app,r,base['dependencies'],dependencies):results.append(r)
        elif (r.get('deferred_stages') and not r.get('pending') and not r.get('analysis_error')
                and result_compatible(app,r,base['dependencies'],dependencies)):
            # A typed row's first answer, a heavy step left out: it is finished when the hands stop, as it would have
            # been had the tab stayed open. It was thrown away here and the row read from the start, showing no answer
            results.append(r);getattr(app,'_arm_heavy_redo',lambda:None)()
        else:results.append(app._blank_result(line))
    same=('\n'.join(old_lines).rstrip('\n')==text.rstrip('\n')
          and tuple(base.get('readings',()))==_readings(app,owner)
          and tuple(base.get('calculations',()))==_calculations(app,owner))
    if same:
        results=results[:len(lines)]+[app._blank_result(line) for line in lines[len(results):]]
        old_lines=list(lines)
        if parked:
            for i,result in enumerate(parked['results']):
                if i<len(results) and reusable_result(result):results[i]=result
        if (base.get('prepared') or {}).get('context') is not None:
            import analysis_async
            analysis_async._save_context(app,text,base['prepared'])
    if not choices_moved(base['dependencies'],dependencies):
        # the units were built with the choice memory of their time (2026-10-24): after it moved they are built again
        app._units_cache.update(base.get('units',{}))
        app._suspect_units_cache.update(base.get('suspect',{}))
    if same and parked:
        app._units_cache.update(parked.get('units',{}))
        app._suspect_units_cache.update(parked.get('suspect_units',{}))
    app._prev_lines=old_lines;app.line_results=results
    app._analyze_ctx=base.get('ctx')
    prepared=base.get('prepared') or {}
    app._attested_surfaces=prepared.get('attested',{})
    app._line_words_cache=dict(prepared.get('words',{}))
    app._analyze_dependencies=dependencies
    app._analyze_readings=tuple(base.get('readings',()))
    app._analyze_calculations=tuple(base.get('calculations',()))
    app._analyze_text='\n'.join(old_lines)
    app._analyze_work=work.token(app)
    app._analyze_todo=[i for i,r in enumerate(results) if not reusable_result(r) and not r.get('deferred_stages')]
    app._analyze_pos=0;app._analyze_units_only=False


def rebase_background(app,state):
    """Reuse a dirty tab's rows after preparing its current context off Tk."""
    base=state.pop('previous',None)
    if not base or not same_model_state(base.get('dependencies'),state['dependencies']):return
    from analysis_context import previous_line_of,reuse_rows,signature
    from analysis_async import _background_readings
    from context_vec import build_nearby_words
    lines=state['lines'];words=state['words']
    results=[dict(original=line,corrected=line,pending=True) for line in lines]
    signatures={i:signature(build_nearby_words(len(lines),i,lambda k:words.get(lines[k],[])),
        _background_readings(state,i),_background_readings(state,i,'calculations'),
        previous_line_of(lines,i)) for i in range(len(lines))}
    previous=[r for r in base['results'] if result_compatible(app,r,base['dependencies'],state['dependencies'])]
    reuse_rows(results,list(range(len(lines))),previous,signatures,base.get('ctx'),state['ctx'],state['attested'])
    state['results']=[r if reusable_result(r) else None for r in results]


def saved_partial(app,text,owner):
    """The rows the saved file holds for a tab not yet opened, for the background: finished rows as they are, and the
    rows it cannot vouch for (a word has moved since the file was read) left for when the tab is opened, when they
    are shown as they are and read again. Without this every restart read those rows again from the first row
    (2026-11-05, 35 of the 35 rows sent in the first minute were in the file)."""
    key=text.rstrip('\n')
    partial=(getattr(app,'_analysis_partial',None) or {}).get(key)
    current=state_key(app)
    previous=learned_since(app,getattr(app,'_analysis_partial_state',None),current)
    lines=text.split('\n')
    if (not partial or previous is None or not same_model_state(previous,current) or len(partial)>len(lines)
            or _readings(app,owner) or _calculations(app,owner) or key in getattr(app,'_analysis_stale',())):
        return {}
    results=[None]*len(lines);skip=set()
    for i,r in enumerate(partial):
        if not r or r.get('original')!=lines[i]:continue
        if previous==current and reusable_result(r):results[i]=r
        elif reusable_result(r) or kept_answer(r):skip.add(i)
    return dict(results=results,skip=skip) if any(results) or skip else {}


def background_values(app,text,owner,saved):
    """Reuse completed corrections without borrowing another owner's evidence."""
    if saved is not None:
        return dict(results=list(saved['results']),ctx=saved['prepared']['context'],
            words=dict(saved['prepared']['words']),attested=saved['prepared']['attested'],
            units=dict(saved['units']),suspect_units=dict(saved['suspect']))
    results=text_results(app,text,owner)
    if results is None:
        base=previous_values(app,owner)
        if not base:return saved_partial(app,text,owner)
        if not same_model_state(base.get('dependencies'),state_key(app)):return {}
        if choices_moved(base.get('dependencies'),state_key(app)):
            return dict(previous=base,units={},suspect_units={})      # built again with the new choices
        return dict(previous=base,units=dict(base.get('units',{})),suspect_units=dict(base.get('suspect',{})))
    units,suspect=getattr(app,'_tab_units_cache',{}).get(text,({},{}))
    return dict(results=list(results),units=dict(units),suspect_units=dict(suspect))


def remember_background(app,state):
    return _save(app,state['owner'],state['text'],state['results'],
        dict(context=state['ctx'],attested=state.get('attested',{}),words=state.get('words',{})),
        state.get('units',{}),state.get('suspect_units',{}),state.get('dependencies'),state.get('readings',()),state.get('calculations',()))

def changed_reading_rows(app, previous, lines, head, tail):
    """Compare line-local evidence; moving an intact occurrence is not a new fact."""
    from analysis_work import Document
    old=tuple(getattr(app,'_analyze_readings',()))
    new=_readings(app,work.owner(app))
    old_calculations=tuple(getattr(app,'_analyze_calculations',()))
    new_calculations=_calculations(app,work.owner(app))
    if not (old or new or old_calculations or new_calculations):return []
    old_doc=Document(None,'\n'.join(previous));old_doc.occurrences=old
    new_doc=Document(None,'\n'.join(lines));new_doc.occurrences=new
    old_doc.calculations=old_calculations;new_doc.calculations=new_calculations
    matched=[(i,i) for i in range(head)]
    matched.extend((len(previous)-tail+i,len(lines)-tail+i) for i in range(tail))
    return [j for i,j in matched if old_doc.row_readings(i,previous[i])
            != new_doc.row_readings(j,lines[j]) or old_doc.row_calculations(i,previous[i])
            !=new_doc.row_calculations(j,lines[j])]


def background_compatible(app,state):
    """Validate ownership and refresh completed rows after IME-only changes.

    In-flight requests retain their old scope and cannot become completed values.
    """
    owner=state.get('owner')
    current=state_key(app);previous=learned_since(app,state.get('dependencies'),current)
    if (owner is None or not same_model_state(previous,current)
            or model_moved(previous,current)      # its context is from the old store: start from the baseline
            or tuple(state.get('readings',()))!=_readings(app,owner)
            or tuple(state.get('calculations',()))!=_calculations(app,owner)):
        return False
    present=any(work.owner_for_tab(app,tab)==owner and
                (tab.get('text') or '').rstrip('\n')==state.get('text')
                for tab in app.session.tabs)
    if present and previous!=current:
        state['results']=[r if result_compatible(app,r,previous,current) else None for r in state['results']]
        state['dependencies']=current
        state['pos']=next((i for i,r in enumerate(state['results'])
            if display_pending(r,state.get('units',{}),state.get('suspect_units',{}))),len(state['results']))
    return present


def text_results(app,text,owner=None):
    """Only a document without occurrence readings may use shared text values."""
    owner=work.owner(app) if owner is None else owner
    key=text.rstrip('\n')
    if (not key or _readings(app,owner) or _calculations(app,owner)
            or key in getattr(app,'_analysis_stale',())):
        return None
    results=getattr(app,'_analysis_cache',{}).get(key)
    previous=getattr(app,'_analysis_cache_dependencies',{}).get(key)
    current=state_key(app)
    if previous!=current:
        if results is None or not all(result_compatible(app,r,previous,current) for r in results):return None
        app._analysis_cache_dependencies[key]=current
    lines=key.split('\n')
    if (results is None or len(results)!=len(lines)
            or any(not reusable_result(r) or r.get('original')!=line for r,line in zip(results,lines))):
        return None
    return results


def restored_results(app,text,owner=None):
    """The rows of a tab read back from the saved file, after what they may have used has moved: those that cannot
    say keep their answers, to be read again when the hands stop. None when a row is known to be out of date."""
    owner=work.owner(app) if owner is None else owner
    key=text.rstrip(chr(10))
    if (not key or _readings(app,owner) or _calculations(app,owner)
            or key in getattr(app,'_analysis_stale',())):
        return None
    results=getattr(app,'_analysis_cache',{}).get(key)
    previous=getattr(app,'_analysis_cache_dependencies',{}).get(key)
    current=state_key(app)
    lines=key.split(chr(10))
    if results is None or previous is None or previous==current or len(results)!=len(lines):return None
    from analysis_worker import same_model_state
    if not same_model_state(previous,current):return None
    rows=[]
    for result,line in zip(results,lines):
        if not reusable_result(result) or result.get('original')!=line:return None
        if result_compatible(app,result,previous,current):rows.append(result)
        elif restored_without_proof(result):rows.append(keep_answer(result))
        else:return None
    return rows


def park_background(app,state):
    """Merge completed portions of one live owner; identical text is not identity."""
    state=dict(state)
    state['results']=[result if reusable_result(result) else None for result in state['results']]
    owner=state['owner'];cache=getattr(app,'_bg_parked',{})
    old=cache.get(owner)
    if (old and old['text']==state['text'] and old.get('dependencies')==state.get('dependencies')
            and old.get('readings',())==state.get('readings',())
            and old.get('calculations',())==state.get('calculations',())):
        state=dict(state)
        state['results']=[new or (previous if reusable_result(previous) else None)
                          for new,previous in zip(state['results'],old['results'])]
        state['units']={
            **old.get('units',{}),**state.get('units',{})}
        state['suspect_units']={**old.get('suspect_units',{}),**state.get('suspect_units',{})}
        if state.get('ctx') is None:
            for field in ('ctx','words','attested'):state[field]=old.get(field)
    state['pos']=next((i for i,result in enumerate(state['results'])
                      if display_pending(result,state.get('units',{}),state.get('suspect_units',{}))),len(state['results']))
    live={work.owner_for_tab(app,tab) for tab in app.session.tabs}
    cache={key:value for key,value in cache.items() if key in live and key!=owner}
    if owner in live:cache[owner]=state
    app._bg_parked=cache
