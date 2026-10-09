# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Transfer only an explicitly observed fullwidth IME mode to our own input.

No text, composition, history, keyboard hooks or source-window writes are used.
Unknown/closed/halfwidth sources leave the destination's default mode alone.
"""
import ctypes as C
from ctypes import wintypes as W
import sys

class _GuiInfo(C.Structure):
    _fields_=[('cbSize',W.DWORD),('flags',W.DWORD),('hwndActive',W.HWND),
              ('hwndFocus',W.HWND),('hwndCapture',W.HWND),('hwndMenuOwner',W.HWND),
              ('hwndMoveSize',W.HWND),('hwndCaret',W.HWND),('rcCaret',W.RECT)]

_API=None

def _api():
    global _API
    if _API is None:
        user=C.WinDLL('user32',use_last_error=True)
        signatures={
            'GetForegroundWindow':([],W.HWND),
            'GetWindowThreadProcessId':([W.HWND,C.POINTER(W.DWORD)],W.DWORD),
            'GetGUIThreadInfo':([W.DWORD,C.POINTER(_GuiInfo)],W.BOOL),
            'SendMessageTimeoutW':([W.HWND,W.UINT,C.c_size_t,C.c_ssize_t,W.UINT,W.UINT,C.POINTER(C.c_size_t)],C.c_ssize_t),
        }
        for name,(args,result) in signatures.items():
            fn=getattr(user,name);fn.argtypes=args;fn.restype=result
        _API=user
    return _API


def _control(ime,command,value=0):
    result=C.c_size_t()
    # Abort on an unresponsive/destroyed source. Never block the UI indefinitely.
    ok=_api().SendMessageTimeoutW(ime,0x0283,command,value,0x23,40,C.byref(result))
    return int(result.value) if ok else None


def window_mode(hwnd):
    if sys.platform!='win32' or not hwnd:return None
    import ime_watch
    try:
        ime=ime_watch._imm32().ImmGetDefaultIMEWnd(hwnd)
        if not ime:return None
        opened=_control(ime,5)  # IMC_GETOPENSTATUS
        if opened is None:return None
        if not opened:return (False,0)
        conversion=_control(ime,1)  # IMC_GETCONVERSIONMODE
        return None if conversion is None else (True,conversion)
    except (OSError,ValueError):return None


def foreground_fullwidth_mode():
    if sys.platform!='win32':return None
    try:
        user=_api();foreground=user.GetForegroundWindow()
        if not foreground:return None
        thread=user.GetWindowThreadProcessId(foreground,None)
        if not thread:return None
        info=_GuiInfo();info.cbSize=C.sizeof(info)
        if not user.GetGUIThreadInfo(thread,C.byref(info)) or not info.hwndFocus:return None
        focused=info.hwndFocus;mode=window_mode(focused)
        current=_GuiInfo();current.cbSize=C.sizeof(current)
        if (user.GetForegroundWindow()!=foreground or
                not user.GetGUIThreadInfo(thread,C.byref(current)) or current.hwndFocus!=focused):return None
        return mode[1] if mode and mode[0] and mode[1]&0x8 else None
    except (OSError,ValueError):return None


def apply_fullwidth_mode(hwnd,conversion):
    """Caller supplies only its quick Text HWND, after focus/context separation."""
    if sys.platform!='win32' or not hwnd or conversion is None or not conversion&0x8:return False
    import ime_watch
    try:
        imm=ime_watch._imm32();himc=imm.ImmGetContext(hwnd)
        if not himc:return False
        try:
            old=W.DWORD();sentence=W.DWORD()
            if not imm.ImmGetConversionStatus(himc,C.byref(old),C.byref(sentence)):return False
            if old.value!=conversion:imm.ImmSetConversionStatus(himc,conversion,sentence.value)
            if not imm.ImmGetOpenStatus(himc):imm.ImmSetOpenStatus(himc,True)
        finally:imm.ImmReleaseContext(hwnd,himc)
        if window_mode(hwnd)==(True,conversion):return True
        # Some IMEs replace mode during focus activation. Address only our IME
        # window once after activation; failure remains visible to the caller.
        ime=imm.ImmGetDefaultIMEWnd(hwnd)
        if not ime:return False
        if _control(ime,2,conversion) is None:return False  # IMC_SETCONVERSIONMODE
        if _control(ime,6,1) is None:return False  # IMC_SETOPENSTATUS
        return window_mode(hwnd)==(True,conversion)
    except (OSError,ValueError):return False