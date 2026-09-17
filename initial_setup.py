# -*- coding: utf-8 -*-
"""Nonblocking first-run dictionary preparation; public values cross the process."""
import time
from analysis_worker import Worker
import analysis_async


def start(app):
    if getattr(app,'_closing',False) or getattr(app,'_initial_setup',None) is not None:return
    from janome_import import DEFAULT_MAX_WORDS
    rows=[] if len(app.store.to_list())>=DEFAULT_MAX_WORDS else None
    state=dict(rows=rows,pos=0,worker=None,request=None,job=None,failed=False)
    app._initial_setup=state
    app._cancel_analysis_job()
    job=getattr(app,'_after_id',None)
    if job is not None:app.root.after_cancel(job)
    app._after_id=None;app._async_context_scope=None;app._async_request=None
    analysis_async.close(app)
    app.status.config(text='初回の辞書を準備しています。編集できます。')
    if rows is None:
        try:
            state['worker']=Worker()
            state['request']=state['worker'].submit(dict(kind='initial_dictionary'))
        except Exception:
            state['failed']=True;state['rows']=[]
    _schedule(app,state)


def _schedule(app,state,delay=50):
    state['job']=app.root.after(delay,lambda:_step(app,state))


def _step(app,state):
    if getattr(app,'_initial_setup',None) is not state or getattr(app,'_closing',False):return
    state['job']=None
    try:
        if state['rows'] is None:
            rows=state['worker'].poll(state['request'])
            if rows is None:
                _schedule(app,state);return
            state['rows']=rows
            state['worker'].close();state['worker']=None
        # Warmup reads the same store. Apply public entries only after that
        # reader has finished; collecting them can run alongside it.
        if getattr(app,'_warmup',None) is not None:
            _schedule(app,state);return
        rows=state['rows'];started=time.monotonic()
        stop=min(state['pos']+250,len(rows))
        while state['pos']<stop:
            reading,surface,category,world=rows[state['pos']]
            app.store.add(reading,surface,category,world=world)
            state['pos']+=1
            if time.monotonic()-started>.008:break
        if state['pos']<len(rows):
            _schedule(app,state,1);return
    except Exception:
        state['failed']=True;state['rows']=[]
        if state['worker'] is not None:
            state['worker'].close();state['worker']=None
    _finish(app,state)


def _finish(app,state):
    changed=state['pos']>0
    app._initial_setup=None
    if changed:
        try:app.store.save()
        except Exception:state['failed']=True
        app._invalidate_analysis_cache(keep_current=False)
    ready=bool(getattr(getattr(app,'dict_index',None),'ready',False))
    app._mark_setup_done(dictionary=changed and not state['failed'],index=ready)
    app._update_status()
    app.status.config(text=('初回の辞書準備に失敗しました。現在の辞書で続けます。'
        if state['failed'] else '初回の準備が終わりました。そのまま書き始められます。'))
    app._warm_then_analyze()


def close(app):
    state=getattr(app,'_initial_setup',None)
    app._initial_setup=None
    if state is None:return
    job=state.get('job')
    if job is not None:
        try:app.root.after_cancel(job)
        except Exception:pass
    worker=state.get('worker')
    if worker is not None:worker.close()
