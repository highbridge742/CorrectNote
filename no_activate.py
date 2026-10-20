# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""A click on a button that does not make CorrectNote the active app (Windows).

2026-10-19 うにさん「別アプリアクティブ中に、本アプリの単語帳ボタンを直接クリックした場合は、
本アプリをアクティブにせずに、単語帳を開いてください」. While another app is in front, the
button answers WM_MOUSEACTIVATE with MA_NOACTIVATE: the click still reaches the button (its
command runs), but CorrectNote's window is not activated and the other app keeps the front
and its text box. With CorrectNote in front, or when the window in front cannot be told,
the message is passed on as before.

The native callback only reads the window in front (no Tk calls, no text)."""
import os
import sys

WM_MOUSEACTIVATE = 0x0021
WM_NCDESTROY = 0x0082
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
BN_CLICKED = 0
MA_NOACTIVATE = 3

_KEEP = {}      # hwnd -> the callback, kept alive while the window lives


def _foreground_process():
    """The process of the window in front, or None when it cannot be told."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32')
        user.GetForegroundWindow.restype = wintypes.HWND
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        front = user.GetForegroundWindow()
        if not front:
            return None
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(front, ctypes.byref(pid))
        return pid.value or None
    except Exception:
        return None


def other_app_in_front():
    """True when CorrectNote is not the app in front (Windows only).

    No window in front counts as "not CorrectNote": at the moment of a click on an inactive
    window Windows can report none (うにさんの記録 2026-10-19: front=0 on WM_MOUSEACTIVATE,
    which let the click activate CorrectNote)."""
    if sys.platform != 'win32':
        return False
    front = _foreground_process()
    return front != os.getpid()


_LAST_OUTSIDE = None     # (hwnd, pid, time) of the other app last seen in front over the button


def _note_outside():
    """Remember the other app in front while the pointer is over the button: by the time of the
    click Windows has already taken the front away from it (うにさんの記録 2026-10-19:
    front=0 on WM_MOUSEACTIVATE), and the word book must give the front back to it."""
    global _LAST_OUTSIDE
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        import time
        from ctypes import wintypes
        user = ctypes.WinDLL('user32')
        user.GetForegroundWindow.restype = wintypes.HWND
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        front = user.GetForegroundWindow()
        if not front:
            return
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(front, ctypes.byref(pid))
        if pid.value and pid.value != os.getpid():
            _LAST_OUTSIDE = (int(front), pid.value, time.monotonic())
    except Exception:
        pass


_POSTED_AT = None        # time of the last click this module posted to a button


def posted_recently(within=0.5):
    """A click was posted by the button's subclass just now. Tk's own button handling can then
    run the command a second time (うにさんの記録 2026-10-19: ~30-110 ms later)."""
    import time
    return _POSTED_AT is not None and 0 <= time.monotonic() - _POSTED_AT < within


def recent_outside(max_age=30.0):
    """(hwnd, pid) of the other app last seen in front over the button, if recent."""
    import time
    seen = _LAST_OUTSIDE
    if seen is None or time.monotonic() - seen[2] > max_age:
        return None
    return seen[0], seen[1]


def install(widget):
    """Make clicks on `widget` (a Tk widget with its own window) not activate CorrectNote while
    another app is in front. True when installed."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes as c
        from ctypes import wintypes as W
        hwnd = int(widget.winfo_id())
        if hwnd in _KEEP:
            return True
        cc = c.WinDLL('comctl32', use_last_error=True)
        proc_type = c.WINFUNCTYPE(c.c_ssize_t, W.HWND, W.UINT, c.c_size_t, c.c_ssize_t, c.c_size_t, c.c_size_t)
        cc.SetWindowSubclass.argtypes = [W.HWND, proc_type, c.c_size_t, c.c_size_t]
        cc.SetWindowSubclass.restype = W.BOOL
        cc.RemoveWindowSubclass.argtypes = [W.HWND, proc_type, c.c_size_t]
        cc.RemoveWindowSubclass.restype = W.BOOL
        cc.DefSubclassProc.argtypes = [W.HWND, W.UINT, c.c_size_t, c.c_ssize_t]
        cc.DefSubclassProc.restype = c.c_ssize_t

        user = c.WinDLL('user32')
        user.PostMessageW.argtypes = [W.HWND, W.UINT, c.c_size_t, c.c_ssize_t]; user.PostMessageW.restype = W.BOOL
        user.GetClientRect.argtypes = [W.HWND, c.POINTER(W.RECT)]; user.GetClientRect.restype = W.BOOL
        state = {'pressed': False}
        import focus_trace

        def inside(h, lp):
            x = c.c_short(lp & 0xffff).value
            y = c.c_short((lp >> 16) & 0xffff).value
            rect = W.RECT()
            return bool(user.GetClientRect(h, c.byref(rect))) and 0 <= x < rect.right and 0 <= y < rect.bottom

        def message(h, msg, wp, lp, uid, ref):
            try:
                if msg == WM_MOUSEMOVE:
                    _note_outside()
                elif msg == WM_MOUSEACTIVATE:
                    _note_outside()
                    behind = other_app_in_front()
                    focus_trace.log('button WM_MOUSEACTIVATE other_app_in_front=%s front=%s'
                                    % (behind, focus_trace.foreground()))
                    if behind:
                        return MA_NOACTIVATE
                elif msg in (WM_LBUTTONDOWN, WM_LBUTTONDBLCLK):
                    # The native BUTTON control takes the keyboard focus on a press. With another
                    # app in front that activates CorrectNote's window even without the mouse
                    # activation (2026-10-19 うにさん「アプリが前面に出て下がりませんでした」);
                    # with CorrectNote in front it takes the focus from the text being typed
                    # (うにさん「フォーカスが外れて、そのまま文字を打てない」). So the press never
                    # reaches the control.
                    focus_trace.log('button press kept from the control; front', focus_trace.foreground())
                    state['pressed'] = True
                    return 0
                elif msg == WM_LBUTTONUP and state['pressed']:
                    # The release over the button is the click: hand Tk the click the way its
                    # own reflection of the control's notification does (Tk's button window
                    # takes BN_CLICKED, which is 0, with non-zero parameters; measured on Tk
                    # 8.6.9 and 8.6.12), posted, so the command runs in Tk's own event loop
                    # and not from here.
                    state['pressed'] = False
                    if inside(h, lp):
                        global _POSTED_AT
                        import time
                        focus_trace.log('button release: click posted; front', focus_trace.foreground())
                        _POSTED_AT = time.monotonic()
                        user.PostMessageW(h, BN_CLICKED, 1, int(h))
                    return 0
            except Exception:
                pass
            result = cc.DefSubclassProc(h, msg, wp, lp)
            if msg == WM_NCDESTROY:
                cc.RemoveWindowSubclass(h, proc, uid)
                _KEEP.pop(int(h or 0), None)
            return result
        proc = proc_type(message)
        if not cc.SetWindowSubclass(hwnd, proc, 1, 0):
            return False
        _KEEP[hwnd] = proc
        return True
    except Exception:
        return False
