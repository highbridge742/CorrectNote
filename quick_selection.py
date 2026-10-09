# -*- coding: utf-8 -*-
"""One explicit selection transfer per quick-input opening; no monitoring."""
import os,threading,time
from selection_windows import source_now,MAX_TEXT
from selection_clipboard import read_for_opening as read_selection


def local_selection(app,source):
    if source is None or source.process!=os.getpid():return None
    widget=app.root.focus_get()
    if widget not in (getattr(app,'editor',None),getattr(app,'result_view',None)):return None
    try:
        ranges=widget.tag_ranges('sel')
        if len(ranges)!=2:return None
        value=widget.get(*ranges)
        return value if len(value)<=MAX_TEXT else None
    except Exception:return None


def insert_selection(app,value):
    if not isinstance(value,str) or not value or len(value)>MAX_TEXT:return
    text=app._quick_text
    from text_edit import undo_group
    value=value.replace('\r\n','\n').replace('\r','\n')
    with undo_group(text):text.insert('insert',value)
    text.see('insert')


class SelectionOpening:
    def __init__(self,app,reader=None,snapshot=None,clock=time.monotonic):
        self.app=app;self.reader=reader or read_selection;self.snapshot=snapshot or source_now;self.clock=clock
        self.job=None;self.cancelled=None;self.token=None;self.closed=False
        self.lock=threading.Lock()

    def cancel(self):
        if self.cancelled is not None:self.cancelled.set()
        self.cancelled=None;self.token=None
        if self.job is not None:self.app.root.after_cancel(self.job)
        self.job=None

    def close(self):self.closed=True;self.cancel()

    def open(self,trigger=None):
        self.cancel()
        if self.closed:return
        app=self.app
        win=getattr(app,'_quick_win',None)
        if win is not None:
            try:visible=win.winfo_exists() and win.state()!='iconic'
            except Exception:visible=False
            if visible:
                app._show_quick_capture(trigger,None,None);return
        import quick_ime
        source=self.snapshot();mode=quick_ime.foreground_fullwidth_mode()
        if source is not None and source!=self.snapshot():return
        if source is None or source.process==os.getpid():
            value=local_selection(app,source)
            app._show_quick_capture(trigger,mode,value);return
        # Menu/toolbar calls originate in this app. Only the explicit global
        # hotkey entry may read a different app; direct/internal calls cannot.
        if trigger not in ('insert','minus'):
            app._show_quick_capture(trigger,mode,None);return
        # A slow provider may still be returning after an earlier deadline.
        # Do not accumulate workers or delay the editor behind that provider.
        if not self.lock.acquire(False):
            app._show_quick_capture(trigger,mode,None);return
        cancelled=self.cancelled=threading.Event();token=self.token=object()
        deadline=self.clock()+.65;result=[];done=threading.Event()
        def collect():
            try:
                value=self.reader(source,deadline,cancelled)
                if not cancelled.is_set():result.append(value)
            except Exception:pass
            finally:self.lock.release();done.set()
        threading.Thread(target=collect,name='CorrectNoteSelection',daemon=True).start()
        def poll():
            self.job=None
            if self.closed or token is not self.token:return
            if source!=self.snapshot():self.cancel();return
            if done.is_set() or self.clock()>=deadline:
                value=result[0] if done.is_set() and result else None
                self.cancel()
                app._show_quick_capture(trigger,mode,value)
            else:self.job=app.root.after(12,poll)
        self.job=app.root.after(12,poll)


def open_quick(app,trigger=None):
    controller=getattr(app,'_selection_opening',None)
    if controller is None:
        controller=app._selection_opening=SelectionOpening(app)
    controller.open(trigger)
