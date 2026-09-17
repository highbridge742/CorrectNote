# -*- coding: utf-8 -*-
"""Tk-side scheduling for the isolated engine. Only completed values cross back."""
import traceback
import analysis_work_app as input_work
from analysis_worker import Worker,snapshot,state_key


def _request(app, task, scope):
    worker=getattr(app,'_correction_worker',None)
    if worker is not None and not worker.process.is_alive():
        worker.close();worker=None;app._worker_state=None
    if worker is None:
        worker=app._correction_worker=Worker()
    state=state_key(app)
    data=snapshot(app) if getattr(app,'_worker_state',None)!=state else None
    identifier=worker.submit(task,data)
    app._worker_state=state
    app._async_request=(scope,identifier)
    return identifier


def _poll(app, scope):
    pending=getattr(app,'_async_request',None)
    if not pending or pending[0]!=scope:return False,None
    result=app._correction_worker.poll(pending[1])
    if result is not None:app._async_request=None
    return True,result


def _error(app):
    app._analyze_error_reported=True
    app._analyze_last_error=traceback.format_exc()
    traceback.print_exc()
    try:app.status.config(text='解析でエラーが起きています（コンソール参照）')
    except Exception:pass


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
    except Exception:
        app._async_context_scope=None;_error(app);return None
    def complete():
        if (getattr(app,'_async_context_scope',None)!=scope or
                input_work.token(app)!=scope[1] or state_key(app)!=scope[2]):
            if getattr(app,'_async_context_scope',None)==scope:app._async_context_scope=None
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
        except Exception:
            app._async_context_scope=None;_error(app)
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
                    readings=input_work.line_readings(app,i,lines),attested=getattr(app,'_attested_surfaces',{}))
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
            app.line_results[i]=value['result']
            _unit_values(app,value['result'],value)
        except Exception:
            _error(app)
            app._async_request=None
            res=dict(app._blank_result(lines[i]));res.pop('pending',None)
            res['analysis_error']=True;app.line_results[i]=res
            _unit_values(app,res,dict(corrected_units=(lines[i],[]),original_units=(lines[i],[])))
        app._analyze_pos+=1
        return  # Let Tk paint and reprioritise before sending the next row.


def background_step(app,st):
    if st['ctx'] is not None:
        while st['pos'] < len(st['lines']):
            i=st['pos']
            if st['results'][i] is not None:
                st['pos']+=1
            elif st['lines'][i]=='':
                result=dict(app._blank_result(''));result.pop('pending',None)
                st['results'][i]=result;st['pos']+=1
            else:
                break
        if st['pos']>=len(st['lines']):return
    scope=('background',st['owner'],st['work_epoch'],state_key(app),st['text'],st['pos'],st['ctx'] is None)
    present,value=_poll(app,scope)
    if not present:
        if st['ctx'] is None:
            value=cached_context(app,st['text'])
            if value is None:_request(app,dict(kind='prepare',lines=st['lines']),scope)
        else:
            i=st['pos']
            from context_vec import build_nearby_words
            words=st['words'];lines=st['lines']
            nearby=build_nearby_words(len(lines),i,lambda k:words.get(lines[k],[]) if 0<=k<len(lines) else [])
            _request(app,dict(kind='line',line=lines[i],context=st['ctx'],input_method=(app.settings.get('input_method') or 'kana'),
                nearby=nearby,attested=st['attested'],
                recent=app.recent_words.words() if getattr(app,'recent_words',None) is not None else (),
                readings=_background_readings(st,i)),scope)
    if value is None:return
    if st['ctx'] is None:
        _save_context(app,st['text'],value)
        st['ctx']=value['context'];st['words']=value['words'];st['attested']=value['attested']
        st.setdefault('units',{});st.setdefault('suspect_units',{})
    else:
        res=value['result'];st['results'][st['pos']]=res;st['pos']+=1
        key=(res['original'],res['corrected'])
        st['units'][key]=value['corrected_units']
        st['suspect_units'][key+(False,)]=value['original_units']
        st['suspect_units'][key+(True,)]=value['corrected_units']


def close(app):
    worker=getattr(app,'_correction_worker',None)
    if worker is not None:worker.close()
    app._correction_worker=None;app._worker_state=None

def _background_readings(state,index):
    from analysis_work import Document
    readings=tuple(state.get('readings',()))
    if not readings:return ()
    document=state.get('_reading_document')
    if document is None or document.text!=state['text']:
        document=Document(state['owner'],state['text']);state['_reading_document']=document
    document.occurrences=readings
    return document.row_readings(index,state['lines'][index])
