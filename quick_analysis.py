# -*- coding: utf-8 -*-
"""Nonblocking quick-input correction, owned by the current widget and edit generation."""
import traceback
import analysis_work_app as input_work
from analysis_worker import Worker,WorkerExitedError,snapshot,state_key


def _scope(app):
    widget=getattr(app,'_quick_text',None)
    if widget is None:return None
    text=widget.get('1.0','end-1c')
    return input_work.quick_document(app,text).work(state_key(app))


def _schedule(app,delay=40):
    app._quick_after_id=app.root.after(delay,app._analyze_quick)


def _composing(app):
    import ime_watch
    return bool(ime_watch.composition_active(app._quick_text.winfo_id()))


def defer_f2(app):
    app._quick_f2_pending=(_scope(app),app._quick_text.index('insert'))


def _f2_ready(app,scope):
    pending=getattr(app,'_quick_f2_pending',None)
    app._quick_f2_pending=None
    if pending and pending==(scope,app._quick_text.index('insert')):
        app._on_quick_f2()


def _cancel_idle_release(app):
    identifier=getattr(app,'_quick_idle_after_id',None)
    if identifier:
        try:app.root.after_cancel(identifier)
        except Exception:pass
    app._quick_idle_after_id=None


def _prepare_composition(app):
    # Opening the quick window or its first IME composition gives the child
    # time to prepare public lexical evidence. No text is analysed.
    if getattr(app,'_quick_composition_prepared',False):return
    worker=getattr(app,'_quick_worker',None)
    if worker is None or not worker.process.is_alive():
        if worker is not None:worker.close()
        worker=Worker();app._quick_worker=worker;app._quick_worker_state=None
    dependencies=state_key(app)
    data=snapshot(app) if getattr(app,'_quick_worker_state',None)!=dependencies else None
    worker.submit(dict(kind='quick_prepare'),data)
    app._quick_worker_state=dependencies
    app._quick_composition_prepared=True



def prepare(app):
    if getattr(app,'_quick_text',None) is None or getattr(app,'_quick_job',None) is not None:
        return
    try:_prepare_composition(app)
    except Exception:
        # Optional preparation is not retried by timers. Real correction has
        # its own process recovery and reports actual analysis failures.
        app._quick_composition_prepared=True
        traceback.print_exc()


def schedule_prepare(app):
    widget=getattr(app,'_quick_text',None)
    if widget is None:return
    _cancel_idle_release(app)
    if (getattr(app,'_quick_composition_prepared',False)
            or getattr(app,'_quick_prepare_after_id',None)):
        return
    def ready():
        if (getattr(app,'_quick_text',None) is not widget
                or getattr(app,'_quick_prepare_after_id',None)!=identifier):return
        app._quick_prepare_after_id=None
        prepare(app)
    identifier=app.root.after(40,ready)
    app._quick_prepare_after_id=identifier


def start(app):
    input_work.drain_quick_readings(app)
    scope=_scope(app)
    if scope is None:return
    _cancel_idle_release(app)
    pending=getattr(app,'_quick_f2_pending',None)
    if pending and pending[0]!=scope:app._quick_f2_pending=None
    if _composing(app):
        prepare(app)
        _schedule(app,80)
        return
    job=getattr(app,'_quick_job',None)
    try:
        if job is None or job['scope']!=scope:
            worker=getattr(app,'_quick_worker',None)
            if worker is None or not worker.process.is_alive():
                if worker is not None:worker.close()
                worker=Worker();app._quick_worker=worker;app._quick_worker_state=None
            dependencies=state_key(app)
            state=(snapshot(app) if getattr(app,'_quick_worker_state',None)!=dependencies else None)
            from quote_calculator import displayed_calculations
            displayed={row:displayed_calculations(record)
                       for record,row in app._autofix_live_records(w=app._quick_text)}
            lines=scope.source.split('\n');doc=input_work.quick_document(app,scope.source)
            task=dict(kind='quick',lines=lines,input_method=(app.settings.get('input_method') or 'kana'),
                      attested=tuple(getattr(app,'_attested_surfaces',{}) or ()),
                      readings={i:doc.row_readings(i,line) for i,line in enumerate(lines)},
                      calculations={i:doc.row_calculations(i,line)+displayed.get(i+1,())
                                    for i,line in enumerate(lines)})
            identifier=worker.submit(task,state)
            app._quick_composition_prepared=True
            app._quick_worker_state=dependencies
            job=dict(scope=scope,identifier=identifier,value=None);app._quick_job=job
        if job['value'] is None:job['value']=app._quick_worker.poll(job['identifier'])
        if job['value'] is None:
            _schedule(app)
            return
        if scope!=_scope(app):
            _schedule(app)
            return
        if _composing(app):
            _schedule(app,80)
            return
        value=job['value'];app._quick_job=None
        again=app._finish_quick_analysis(scope.source,value['results'],value['units'],value['corrected_units'])
        if again:
            pending=getattr(app,'_quick_f2_pending',None)
            if pending and pending[0]==scope:
                app._quick_f2_pending=(_scope(app),app._quick_text.index('insert'))
        else:_f2_ready(app,scope)
    except Exception as error:
        app._quick_job=None
        if isinstance(error,WorkerExitedError) and getattr(app,'_quick_worker_retry',None)!=scope:
            app._quick_worker_retry=scope;app._quick_worker.close();app._quick_worker=None
            app._quick_worker_state=None;_schedule(app)
            return
        app._quick_f2_pending=None
        traceback.print_exc()
        try:app.status.config(text='簡易入力の解析でエラーが起きています（コンソール参照）')
        except Exception:pass


def close(app,keep_idle_worker=False):
    input_work.close_quick_readings(app)
    _cancel_idle_release(app)
    for name in ('_quick_after_id','_quick_prepare_after_id'):
        identifier=getattr(app,name,None)
        if identifier:
            try:app.root.after_cancel(identifier)
            except Exception:pass
    app._quick_prepare_after_id=None
    worker=getattr(app,'_quick_worker',None)
    retain=(keep_idle_worker and getattr(app,'_quick_job',None) is None
            and worker is not None and worker.process.is_alive())
    app._quick_after_id=None;app._quick_job=None;app._quick_f2_pending=None
    app._quick_corrected_units=();app._quick_units_text=None
    if not retain:
        if worker is not None:worker.close()
        app._quick_worker=None
    # A reopened widget starts a fresh document context. Keep only the child
    # and its public lexical preparation; set_state clears per-document caches.
    app._quick_worker_state=None
    app._quick_worker_retry=None
    app._quick_composition_prepared=False
    if retain:
        def release():
            if getattr(app,'_quick_idle_after_id',None)!=identifier:return
            app._quick_idle_after_id=None
            if (getattr(app,'_quick_worker',None) is worker
                    and getattr(app,'_quick_text',None) is None
                    and getattr(app,'_quick_job',None) is None):
                worker.close();app._quick_worker=None;app._quick_worker_state=None
        identifier=app.root.after(60000,release)
        app._quick_idle_after_id=identifier