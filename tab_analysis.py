# -*- coding: utf-8 -*-
"""Volatile completed values for currently open documents, including IME ranges.

No history is written. Shared text-only disk caches remain a separate concern.
"""
from analysis_worker import state_key
from analysis_cache import reusable_result
import analysis_work_app as work


def _readings(app, owner):
    doc=getattr(app,'_input_documents',{}).get(owner)
    if doc is None and owner==work.owner(app):doc=getattr(app,'_input_document',None)
    return tuple(doc.occurrences) if doc is not None else ()


def _registry(app):
    live={work.owner_for_tab(app,tab) for tab in app.session.tabs}
    cache=getattr(app,'_completed_tabs',{})
    for owner in list(cache):
        if owner not in live:cache.pop(owner,None)
    app._completed_tabs=cache
    return cache


def completed(app,text,owner=None):
    owner=work.owner(app) if owner is None else owner
    saved=_registry(app).get(owner)
    if (saved and saved['text']==text.rstrip('\n') and saved['dependencies']==state_key(app)
            and saved['readings']==_readings(app,owner)):
        return saved
    return None


def _save(app,owner,text,results,prepared,units,suspect,dependencies,readings):
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
        readings=tuple(readings),units={k:v for k,v in units.items() if k in pairs},
        suspect={k:v for k,v in suspect.items() if k[:2] in pairs})
    # Use the existing aggregate line budget, rather than evicting a fourth tab.
    from analysis_cache import MAX_CACHED_LINES
    total=sum(len(item['results']) for item in cache.values())
    for older in list(cache):
        if total<=MAX_CACHED_LINES or older==owner:break
        total-=len(cache.pop(older)['results'])
    return True


def remember(app):
    if (getattr(app,'_analyze_work',None)!=work.token(app)
            or getattr(app,'_analyze_pos',0)<len(getattr(app,'_analyze_todo',()))):return False
    owner=work.owner(app)
    readings=tuple(getattr(app,'_analyze_readings',()))
    if readings!=_readings(app,owner):return False
    prepared=dict(context=getattr(app,'_analyze_ctx',{}),attested=getattr(app,'_attested_surfaces',{}),
                  words=dict(getattr(app,'_line_words_cache',{})))
    return _save(app,owner,app._analyze_text,app.line_results,prepared,
        getattr(app,'_units_cache',{}),getattr(app,'_suspect_units_cache',{}),
        getattr(app,'_analyze_dependencies',None),readings)


def remember_background(app,state):
    return _save(app,state['owner'],state['text'],state['results'],
        dict(context=state['ctx'],attested=state.get('attested',{}),words=state.get('words',{})),
        state.get('units',{}),state.get('suspect_units',{}),state.get('dependencies'),state.get('readings',()))

def changed_reading_rows(app, previous, lines, head, tail):
    """Compare line-local evidence; moving an intact occurrence is not a new fact."""
    from analysis_work import Document
    old=tuple(getattr(app,'_analyze_readings',()))
    new=_readings(app,work.owner(app))
    if not old and not new:return []
    old_doc=Document(None,'\n'.join(previous));old_doc.occurrences=old
    new_doc=Document(None,'\n'.join(lines));new_doc.occurrences=new
    matched=[(i,i) for i in range(head)]
    matched.extend((len(previous)-tail+i,len(lines)-tail+i) for i in range(tail))
    return [j for i,j in matched if old_doc.row_readings(i,previous[i])
            != new_doc.row_readings(j,lines[j])]


def background_compatible(app,state):
    """Completed portions survive a tab switch, while in-flight requests do not."""
    owner=state.get('owner')
    if (owner is None or state.get('dependencies')!=state_key(app)
            or tuple(state.get('readings',()))!=_readings(app,owner)):
        return False
    return any(work.owner_for_tab(app,tab)==owner and
               (tab.get('text') or '').rstrip('\n')==state.get('text')
               for tab in app.session.tabs)


def text_results(app,text,owner=None):
    """Only a document without occurrence readings may use shared text values."""
    owner=work.owner(app) if owner is None else owner
    key=text.rstrip('\n')
    if (not key or _readings(app,owner) or key in getattr(app,'_analysis_stale',())
            or getattr(app,'_analysis_cache_dependencies',{}).get(key)!=state_key(app)):
        return None
    results=getattr(app,'_analysis_cache',{}).get(key)
    lines=key.split('\n')
    if (results is None or len(results)!=len(lines)
            or any(not reusable_result(r) or r.get('original')!=line for r,line in zip(results,lines))):
        return None
    return results


def park_background(app,state):
    """Merge completed portions of one live owner; identical text is not identity."""
    state=dict(state)
    state['results']=[result if reusable_result(result) else None for result in state['results']]
    owner=state['owner'];cache=getattr(app,'_bg_parked',{})
    old=cache.get(owner)
    if (old and old['text']==state['text'] and old.get('dependencies')==state.get('dependencies')
            and old.get('readings',())==state.get('readings',())):
        state=dict(state)
        state['results']=[new or (previous if reusable_result(previous) else None)
                          for new,previous in zip(state['results'],old['results'])]
        state['units']={
            **old.get('units',{}),**state.get('units',{})}
        state['suspect_units']={**old.get('suspect_units',{}),**state.get('suspect_units',{})}
        if state.get('ctx') is None:
            for field in ('ctx','words','attested'):state[field]=old.get(field)
    state['pos']=next((i for i,result in enumerate(state['results']) if result is None),len(state['results']))
    live={work.owner_for_tab(app,tab) for tab in app.session.tabs}
    cache={key:value for key,value in cache.items() if key in live and key!=owner}
    if owner in live:cache[owner]=state
    while len(cache)>app.BG_PARKED_MAX:cache.pop(next(iter(cache)))
    app._bg_parked=cache
