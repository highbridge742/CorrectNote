# -*- coding: utf-8 -*-
"""Read explicit IME result pairs while their native message is live.

Only the owned editor HWND is observed. The callback never calls Tcl/Tk,
changes an IME context, or consumes its result. Bracket completion observes
actual results while native Tk delivery remains the only text insertion path.
A normal Tk timer drains the
pending pairs. No composition text, timestamps, or history are persisted.
"""
from collections import deque
import sys

WM_IME_STARTCOMPOSITION=0x010D
WM_IME_ENDCOMPOSITION=0x010E
WM_IME_COMPOSITION=0x010F
WM_NCDESTROY=0x0082
_LIVE={}


class ResultEvents:
    def __init__(self,hwnd):
        from ime_commit_ranges import CommitRanges
        self.ranges=CommitRanges()
        self.hwnd=0;self.pending=deque(maxlen=64);self._proc=None;self.completion=None;self.expected_completion=None
        if sys.platform!='win32' or not hwnd:return
        import ctypes as C
        from ctypes import wintypes as W
        self._uid=id(self)
        self._type=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,C.c_size_t,
                                C.c_ssize_t,C.c_size_t,C.c_size_t)
        dll=self._dll=C.WinDLL('comctl32')
        dll.SetWindowSubclass.argtypes=[W.HWND,self._type,C.c_size_t,C.c_size_t]
        dll.SetWindowSubclass.restype=W.BOOL
        dll.RemoveWindowSubclass.argtypes=[W.HWND,self._type,C.c_size_t]
        dll.RemoveWindowSubclass.restype=W.BOOL
        dll.DefSubclassProc.argtypes=[W.HWND,W.UINT,C.c_size_t,C.c_ssize_t]
        dll.DefSubclassProc.restype=C.c_ssize_t
        user=C.WinDLL('user32');kernel=C.WinDLL('kernel32')
        user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
        user.GetWindowThreadProcessId.restype=W.DWORD
        kernel.GetCurrentThreadId.argtypes=[];kernel.GetCurrentThreadId.restype=W.DWORD
        if user.GetWindowThreadProcessId(hwnd,None)!=kernel.GetCurrentThreadId():return
        self._proc=self._type(self._message)
        if dll.SetWindowSubclass(hwnd,self._proc,self._uid,0):
            self.hwnd=hwnd;_LIVE[self._uid]=self

    def _message(self,hwnd,message,wparam,lparam,uid,ref):
        try:
            if message==WM_IME_STARTCOMPOSITION:
                self.release_completion()
                self.ranges.begin()
            elif message==WM_IME_ENDCOMPOSITION:
                self.ranges.finish()
            elif message==WM_IME_COMPOSITION:
                from ime_watch import (GCS_RESULTSTR,GCS_RESULTREADSTR,
                    GCS_RESULTCLAUSE,GCS_RESULTREADCLAUSE,read_composition)
                if self.completion is not None and lparam & GCS_RESULTSTR:
                    got=read_composition(hwnd,result_clauses=False) or {}
                    surface=got.get('result','');reading=got.get('result_reading','')
                    if surface and surface==self.expected_completion:
                        self.completion.append((surface,reading))
                flags=GCS_RESULTSTR|GCS_RESULTREADSTR
                if lparam & flags == flags:
                    clause_flags=GCS_RESULTCLAUSE|GCS_RESULTREADCLAUSE
                    got=read_composition(hwnd,result_clauses=lparam & clause_flags == clause_flags)
                    if got and got.get('result') and got.get('result_reading'):
                        self.pending.append((got['result'],got['result_reading']))
                        for surface,reading in (got.get('result_clauses') or
                                ((got['result'],got['result_reading']),)):
                            self.ranges.result(surface,reading)
            elif message==WM_NCDESTROY:
                self.close()
        except Exception:
            pass
        return self._dll.DefSubclassProc(hwnd,message,wparam,lparam)

    def complete_current(self, expected):
        """Observe our explicit result; normal native delivery owns insertion."""
        if not self.hwnd:return False,()
        from ime_watch import complete_composition,read_composition
        self.completion=[];self.expected_completion=expected
        try:
            success=complete_composition(self.hwnd)
            got=read_composition(self.hwnd) or {}
            # A stale result or an unclosed preedit is not commit evidence.
            if success and not got.get('comp') and got.get('result')==expected:
                return success,((got['result'],got.get('result_reading','')),)
            return success,tuple(self.completion)
        finally:
            # No spelling-based suppression extends into later input.
            self.release_completion()

    def release_completion(self, token=None):
        if token is None or self.completion is token:
            self.completion=None;self.expected_completion=None

    def take(self):
        pairs=tuple(self.pending);self.pending.clear();return pairs

    def close(self):
        if self.hwnd and self._dll.RemoveWindowSubclass(self.hwnd,self._proc,self._uid):
            self.hwnd=0;_LIVE.pop(self._uid,None)
        # Retain the callback if detachment failed; otherwise Windows could
        # call freed Python memory. Destruction retries from WM_NCDESTROY.
        self.pending.clear();self.ranges.clear();self.release_completion()
