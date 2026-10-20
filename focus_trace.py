# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""A diagnostic record of which window is in front, for the word book button (off by default).

2026-10-19 うにさん「アプリが前面に出たままです」: the word book button, clicked while another
app is in front, still brought CorrectNote forward on the real machine although the tests
passed. This records what happens around one click, to find out why.

On only while the file `word_book_trace.on` exists in the folder next to app.py
(`tools_local/`). The record goes to `tools_local/word_book_trace.log`: the time since
start, the window messages the button received and answered, every change of the window in
front (its class and whether it is CorrectNote's), and the steps of opening the word book.
No text, no titles of other windows, no history beyond this file (delete it after reading)."""
import os
import sys
import time

_START = time.monotonic()
_ON = None
_HOOK = None
_PROC = None


def _folder():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools_local')


def enabled():
    global _ON
    if _ON is None:
        try:
            _ON = os.path.exists(os.path.join(_folder(), 'word_book_trace.on'))
        except Exception:
            _ON = False
    return _ON


def _describe(hwnd):
    """Class name and whether the window is CorrectNote's (no titles)."""
    if not hwnd or sys.platform != 'win32':
        return '0'
    try:
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32')
        buf = ctypes.create_unicode_buffer(128)
        user.GetClassNameW(wintypes.HWND(hwnd), buf, 128)
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return '%x:%s:%s' % (int(hwnd), buf.value, 'ours' if pid.value == os.getpid() else 'other')
    except Exception:
        return '%x' % int(hwnd)


def foreground():
    if sys.platform != 'win32':
        return '0'
    try:
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32')
        user.GetForegroundWindow.restype = wintypes.HWND
        return _describe(user.GetForegroundWindow())
    except Exception:
        return '?'


def log(*parts):
    if not enabled():
        return
    try:
        line = '%.3f %s\n' % (time.monotonic() - _START, ' '.join(str(p) for p in parts))
        with open(os.path.join(_folder(), 'word_book_trace.log'), 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def start():
    """Record every change of the window in front (EVENT_SYSTEM_FOREGROUND)."""
    global _HOOK, _PROC
    if not enabled() or _HOOK or sys.platform != 'win32':
        return
    try:
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32')
        proto = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                   wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        user.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, proto,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        user.SetWinEventHook.restype = wintypes.HANDLE

        def changed(hook, event, hwnd, obj, child, thread, tick):
            log('foreground ->', _describe(hwnd))
        _PROC = proto(changed)
        _HOOK = user.SetWinEventHook(3, 3, None, _PROC, 0, 0, 0)
        log('trace started; front', foreground())
    except Exception:
        pass
