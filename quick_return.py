# -*- coding: utf-8 -*-
"""Give the focus back to the text box quick input was opened from.

2026-10-14 うにさん: quick input remembers the window and the control that had
the focus when it opened (another app's text box). On closing, if that was a
text box, its window is brought to the front and the box gets the focus
back; with the option on (default), the closed text — already on the
clipboard — is pasted there with Ctrl+V.

Only another app's text box is a target: opened from CorrectNote itself, the
text goes into the memo as before. Nothing happens when the quick window is
not in the foreground at closing (the user went elsewhere) or the box is gone.
"""
import ctypes as C
import os
import sys
from ctypes import wintypes as W
from dataclasses import dataclass

# Class names of common single/multi-line text controls. A control showing a
# caret is taken as a text box too (browsers, Office, Notepad's RichEdit).
TEXT_CLASSES = ('edit', 'richedit', 'scintilla', 'textbox', 'notepad')
# Web content (Chromium-based browsers and apps, Firefox): the page's fields
# live inside this one window and draw their own caret, so neither the class
# nor the system caret tells a text field (2026-10-19 うにさん: the word book
# only copied in a browser). Asking the browser through MSAA / UI Automation
# does not tell either: it names only the page or its outer pane until it has
# switched its accessibility on (measured with Edge, tools_local/quick_focus_20261019).
# Ctrl+V on a part of a page that does not take text does nothing, so such a
# window counts as a place to paste. Explorer, Excel, image editors and the
# like (where Ctrl+V does something else) are still not targets.
WEB_CONTENT_CLASSES = ('chrome_widgetwin', 'chrome_renderwidgethosthwnd', 'mozillawindowclass')
PASTE_DELAY_MS = 80


@dataclass(frozen=True)
class Target:
    foreground: int
    focus: int
    process: int
    thread: int
    text_box: bool


_USER = None


def _user():
    global _USER
    if _USER is None:
        u = C.WinDLL('user32', use_last_error=True)
        for name, args, result in (
                ('GetForegroundWindow', [], W.HWND),
                ('SetForegroundWindow', [W.HWND], W.BOOL),
                ('BringWindowToTop', [W.HWND], W.BOOL),
                ('SetFocus', [W.HWND], W.HWND),
                ('IsWindow', [W.HWND], W.BOOL),
                ('IsIconic', [W.HWND], W.BOOL),
                ('ShowWindow', [W.HWND, C.c_int], W.BOOL),
                ('GetWindowThreadProcessId', [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
                ('AttachThreadInput', [W.DWORD, W.DWORD, W.BOOL], W.BOOL),
                ('GetClassNameW', [W.HWND, W.LPWSTR, C.c_int], C.c_int),
                ('keybd_event', [W.BYTE, W.BYTE, W.DWORD, C.c_size_t], None)):
            fn = getattr(u, name)
            fn.argtypes = args
            fn.restype = result
        _USER = u
    return _USER


def class_name(hwnd):
    buffer = C.create_unicode_buffer(256)
    try:
        _user().GetClassNameW(hwnd, buffer, 256)
    except Exception:
        return ''
    return buffer.value


def is_text_class(name):
    name = (name or '').lower()
    return any(part in name for part in TEXT_CLASSES)


def is_web_content(name):
    """The focused control is a browser's (or a web-based app's) content window."""
    name = (name or '').lower()
    return any(name.startswith(part) for part in WEB_CONTENT_CLASSES)


def capture(source):
    """The return target for a quick-input opening (None if not another app)."""
    if sys.platform != 'win32' or source is None or source.process == os.getpid():
        return None
    focused = class_name(source.focus)
    text_box = is_text_class(focused) or is_web_content(focused)
    if not text_box:
        try:
            from quick_ime import _api, _GuiInfo
            info = _GuiInfo()
            info.cbSize = C.sizeof(info)
            if _api().GetGUIThreadInfo(source.thread, C.byref(info)):
                text_box = bool(info.hwndCaret)
        except Exception:
            pass
    return Target(source.foreground, source.focus, source.process, source.thread, text_box)


SENT = []   # 門で止めた送り（試験はこれを数える・2026-10-27）


def external_input_blocked():
    """外の窓へキー（Ctrl+V・Ctrl+C）を送らない（試験・確かめの中）。文変換と同じ門で、環境変数
    CORRECTNOTE_NO_EXTERNAL_PASTE=1 のとき（2026-10-27・試験が本物の Ctrl+V を前面の窓へ送りかけた）。"""
    return os.environ.get('CORRECTNOTE_NO_EXTERNAL_PASTE') == '1'


def send_ctrl_v(u):
    """いま前面の窓へ Ctrl+V を送る。門が閉じていれば送らずに SENT に残して False。"""
    if external_input_blocked():
        SENT.append('ctrl+v')
        return False
    for vk, flags in ((0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)):   # Ctrl+V
        u.keybd_event(vk, 0, flags, 0)
    return True


def _ours_in_front():
    pid = W.DWORD()
    u = _user()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), C.byref(pid))
    return pid.value == os.getpid()


def restore(target, root, paste=False):
    """Bring the target window forward, focus its box, then paste if asked.

    Returns True when the focus was given back: the target window is in
    front afterwards (2026-10-16). Otherwise nothing is pasted anywhere.

    Call it while the quick-input window is still the window in front, before
    destroying it (2026-10-19 うにさん: opened from A, a visit to app B, back to
    quick input, close — the focus did not go back to A). Destroying the
    active window makes Windows activate the window used last, here B, and
    then "our window is not in front" reads as "the user went elsewhere"."""
    if sys.platform != 'win32' or target is None or not target.text_box:
        return False
    u = _user()
    if not u.IsWindow(target.foreground) or not u.IsWindow(target.focus):
        return False
    if not _ours_in_front():
        return False        # the user is already elsewhere: do not pull them back
    me = C.WinDLL('kernel32').GetCurrentThreadId()
    attached = bool(u.AttachThreadInput(me, target.thread, True))
    try:
        if u.IsIconic(target.foreground):
            u.ShowWindow(target.foreground, 9)      # SW_RESTORE
        u.SetForegroundWindow(target.foreground)
        u.BringWindowToTop(target.foreground)
        u.SetFocus(target.focus)
    finally:
        if attached:
            u.AttachThreadInput(me, target.thread, False)
    if u.GetForegroundWindow() != target.foreground:
        return False        # Windows did not let it come forward: paste nowhere
    if paste:
        def send():
            if u.GetForegroundWindow() != target.foreground:
                return      # something else came forward meanwhile
            send_ctrl_v(u)
        try:
            root.after(PASTE_DELAY_MS, send)
        except Exception:
            pass
    return True
