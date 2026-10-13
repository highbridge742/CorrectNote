"""Worker-thread ownership of a text-free, optional TSF manager connection.

Search candidate/result objects remain in ime_session.resource_scope.
Only the native manager survives those per-request scopes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident
import queue,sys

_CURRENT=ContextVar('correctnote_worker_tsf_connection',default=None)


def _pump_messages():
    """Dispatch only messages belonging to this calling worker thread."""
    if sys.platform!='win32':return True
    import ctypes as C
    from ctypes import wintypes as W
    user=C.WinDLL('user32',use_last_error=True)
    user.PeekMessageW.argtypes=(C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT)
    user.PeekMessageW.restype=W.BOOL
    user.TranslateMessage.argtypes=(C.POINTER(W.MSG),)
    user.TranslateMessage.restype=W.BOOL
    user.DispatchMessageW.argtypes=(C.POINTER(W.MSG),)
    user.DispatchMessageW.restype=C.c_ssize_t
    message=W.MSG()
    # Yield back to the request queue even when a native service posts more
    # messages while handling its previous message.
    for _ in range(64):
        if not user.PeekMessageW(C.byref(message),None,0,0,1):break
        if message.message==0x0012:return False  # WM_QUIT
        user.TranslateMessage(C.byref(message));user.DispatchMessageW(C.byref(message))
    return True


class _Owner:
    def __init__(self):
        self.thread=get_ident();self.connection=None;self.quit=False
    def _check(self):
        if self.thread!=get_ident():raise RuntimeError('TSF connection belongs to another thread')
    def borrow(self):
        self._check();return self.connection
    def publish(self,connection):
        self._check()
        if self.connection is not None:raise RuntimeError('TSF connection already owned')
        self.connection=connection
    def discard(self,connection):
        self._check()
        if self.connection is connection:self.connection=None
        connection.close()
    def pump(self):
        self._check()
        if self.connection is not None and not self.quit:self.quit=not _pump_messages()
        return not self.quit
    def get(self,inbox):
        self._check()
        if self.connection is None:return inbox.get()
        while self.pump():
            try:return inbox.get(timeout=.02)
            except queue.Empty:pass
        return None
    def close(self):
        self._check();connection=self.connection;self.connection=None
        if connection is not None:connection.close()


def current_owner():
    owner=_CURRENT.get()
    return owner if owner is not None and owner.thread==get_ident() else None


@contextmanager
def worker_connection_scope():
    existing=current_owner()
    if existing is not None:
        yield existing;return
    owner=_Owner();token=_CURRENT.set(owner)
    try:yield owner
    finally:
        _CURRENT.reset(token);owner.close()
