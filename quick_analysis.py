# -*- coding: utf-8 -*-
"""Nonblocking quick-input correction, owned by the current widget and edit generation."""
import traceback
import math
import time
import analysis_work_app as input_work
import quick_row_reuse
from analysis_worker import Worker,WorkerExitedError,snapshot,state_key


def _scope(app):
    widget=getattr(app,'_quick_text',None)
    if widget is None:return None
    text=widget.get('1.0','end-1c')
    return input_work.quick_document(app,text).work(state_key(app))


# Start the same committed work early while retaining the prior display pause.
COMPUTE_DELAY_MS = 80
DISPLAY_QUIET_MS = 250


def _pause_identity(scope):
    # Current ownership only; do not retain another copy of input or readings.
    return scope.owner,scope.generation,scope.dependencies


def schedule_change(app):
    scope=_scope(app)
    if scope is None:return
    current=_pause_identity(scope)
    if current==getattr(app,'_quick_pause_identity',None):return
    app._quick_pause_identity=current
    app._quick_display_after=time.monotonic()+DISPLAY_QUIET_MS/1000
    identifier=getattr(app,'_quick_after_id',None)
    if identifier:app.root.after_cancel(identifier)
    _schedule(app,COMPUTE_DELAY_MS)


def refresh_after_mode(app):
    """Revisit display deferred by a mode, without inventing another key pause."""
    if getattr(app,'_quick_text',None) is None or getattr(app,'_quick_after_id',None) is not None:return
    _schedule(app,0)


def _follow_pause_identity(app,scope):
    current=getattr(app,'_quick_pause_identity',None)
    if scope is not None and current and scope.owner is current[0]:
        # Committed readings and our projection can advance the Document
        # without a new typed pause. Follow them without extending its end.
        app._quick_pause_identity=_pause_identity(scope)


def _display_wait_ms(app,scope):
    current=getattr(app,'_quick_pause_identity',None)
    if not current or scope.owner is not current[0]:return 0
    # Explicit F2 already cancels the automatic timer to request current units.
    if getattr(app,'_quick_f2_pending',None)==(scope,app._quick_text.index('insert')):return 0
    return max(0,math.ceil((getattr(app,'_quick_display_after',0)-time.monotonic())*1000))


def _schedule(app,delay=40):
    app._quick_after_id=app.root.after(delay,app._analyze_quick)


def _composing(app):
    import ime_watch
    return bool(ime_watch.composition_active(app._quick_text.winfo_id()))


def defer_f2(app):
    app._quick_f2_pending=(_committed_scope(app),app._quick_text.index('insert'))


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


def queue_idle_prewarm(app,delay=1200):
    """Use quiet time for public resources; never replace a pending correction."""
    widget=getattr(app,'_quick_text',None);worker=getattr(app,'_quick_worker',None)
    if (widget is None or worker is None or getattr(app,'_closing',False)
            or getattr(app,'_quick_prewarm_after_id',None) is not None
            or getattr(worker,'_quick_idle_prewarm_submitted',False) is True):return
    def ready():
        if getattr(app,'_quick_prewarm_after_id',None)!=identifier:return
        app._quick_prewarm_after_id=None
        if (getattr(app,'_closing',False) or getattr(app,'_quick_text',None) is not widget
                or getattr(app,'_quick_worker',None) is not worker
                or not worker.process.is_alive()
                or getattr(worker,'_quick_idle_prewarm_submitted',False) is True
                or getattr(app,'_quick_job',None) is not None
                or getattr(app,'_quick_f2_pending',None) is not None
                or getattr(app,'_quick_worker_state',None)!=state_key(app)
                or time.monotonic()<getattr(app,'_quick_display_after',0)):
            return
        # The composition timer may wait for commit while no text work is
        # active. Public resources do not read or reinterpret preedit text.
        if getattr(app,'_quick_after_id',None) is not None and not _composing(app):return
        try:
            worker.submit(dict(kind='warmup'))
            worker._quick_idle_prewarm_submitted=True
        except Exception:traceback.print_exc()
    identifier=app.root.after(delay,ready)
    app._quick_prewarm_after_id=identifier


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
    queue_idle_prewarm(app)



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


def _committed_scope(app):
    # Both F2 and correction own the same positioned committed evidence.
    scope=_scope(app)
    if scope is None:return
    reserved=_pause_identity(scope)==getattr(app,'_quick_pause_identity',None)
    if input_work.drain_quick_readings(app):
        scope=_scope(app)
        if scope is None:return
        # Follow only the reading update just drained for the reserved edit.
        # A real edit delivered before its KeyRelease still starts a new pause.
        if reserved:_follow_pause_identity(app,scope)
    return scope


def start(app):
    scope=_committed_scope(app)
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
            reusable=quick_row_reuse.select(app,scope,task)
            if reusable:task['reuse']=reusable
            identifier=worker.submit(task,state)
            app._quick_composition_prepared=True
            app._quick_worker_state=dependencies
            job=dict(scope=scope,identifier=identifier,value=None,task=task);app._quick_job=job
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
        remaining=_display_wait_ms(app,scope)
        if remaining:
            _schedule(app,remaining)
            return
        value=job['value'];app._quick_job=None
        quick_row_reuse.remember(app,scope,job['task'],value)
        again=app._finish_quick_analysis(scope.source,value['results'],value['units'],value['corrected_units'])
        if again:
            following=_scope(app)
            _follow_pause_identity(app,following)
            pending=getattr(app,'_quick_f2_pending',None)
            if pending and pending[0]==scope:
                app._quick_f2_pending=(following,app._quick_text.index('insert'))
        else:
            _f2_ready(app,scope)
            queue_idle_prewarm(app)
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
    for name in ('_quick_after_id','_quick_prepare_after_id','_quick_prewarm_after_id'):
        identifier=getattr(app,name,None)
        if identifier:
            try:app.root.after_cancel(identifier)
            except Exception:pass
    app._quick_prepare_after_id=None;app._quick_prewarm_after_id=None
    worker=getattr(app,'_quick_worker',None)
    retain=(keep_idle_worker and getattr(app,'_quick_job',None) is None
            and worker is not None and worker.process.is_alive())
    app._quick_after_id=None;app._quick_job=None;app._quick_f2_pending=None
    app._quick_pause_identity=None;app._quick_display_after=0
    app._quick_corrected_units=();app._quick_units_text=None
    app._quick_row_reuse=None
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