# -*- coding: utf-8 -*-
"""Native assertions for isolated, hidden application windows only."""
import ctypes,sys
from ctypes import wintypes as W


def assert_quick_context_isolation(app):
    if not sys.platform.startswith('win'):return
    imm=ctypes.WinDLL('imm32')
    imm.ImmGetContext.argtypes=[W.HWND];imm.ImmGetContext.restype=W.HANDLE
    imm.ImmReleaseContext.argtypes=[W.HWND,W.HANDLE];imm.ImmReleaseContext.restype=W.BOOL
    class Form(ctypes.Structure):
        _fields_=[('style',W.DWORD),('point',W.POINT),('area',W.RECT)]
    imm.ImmGetCompositionWindow.argtypes=[W.HANDLE,ctypes.POINTER(Form)]
    imm.ImmGetCompositionWindow.restype=W.BOOL
    def context(hwnd):
        value=imm.ImmGetContext(hwnd)
        if value:imm.ImmReleaseContext(hwnd,value)
        return value
    def position(hwnd):
        value=imm.ImmGetContext(hwnd);form=Form()
        try:
            assert value and imm.ImmGetCompositionWindow(value,ctypes.byref(form))
            return form.style,form.point.x,form.point.y
        finally:
            if value:imm.ImmReleaseContext(hwnd,value)
    main=app.root.winfo_id();quick=app._quick_win.winfo_id()
    original=context(main);dedicated=app._quick_himc
    assert original and dedicated and original!=dedicated
    assert quick in app._quick_himc_hwnds, 'Tk writes composition position through its Toplevel client'
    assert all(context(h)==dedicated for h in app._quick_himc_hwnds)
    assert context(app.editor.winfo_id())==original
    app.root.tk.call('tk','caret',app.editor,'-x',41,'-y',71,'-height',20)
    baseline=position(main)
    app.root.tk.call('tk','caret',app._quick_text,'-x',151,'-y',191,'-height',20)
    assert position(main)==baseline, 'Inactive quick input moved the main IME'
    baseline=position(quick)
    app.root.tk.call('tk','caret',app.editor,'-x',43,'-y',73,'-height',20)
    assert position(quick)==baseline, 'Main editor moved the quick-input IME'
    return original
