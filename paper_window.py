# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
本文の欄を透かして、後ろの絵を見せるための Windows の窓の設定（appearance.Paper・2026-11-05）。

Tk の Text は背景に絵を敷けない。行ごとのタグに切れ端を貼ると、絵は窓に固定なのにスクロールのたびに
全部の行を貼り直すことになる（1コマ 70〜130ms。貼り直さなければ 40ms）。そこで欄の地の色を透過色にして
（WS_EX_LAYERED・LWA_COLORKEY）、すぐ後ろの Canvas に描いた絵を見せる。字・選択の色など、地の色以外の
画素はそのまま出る。子の窓に透過を使えるのは Windows 8 から。

透かした画素のマウスの操作は OS が後ろの窓へ渡すので、後ろの Canvas の窓の手続きで本文の欄へ送り直す。
Tk はメッセージを受けた窓で操作を決めるので、Text の bind・カーソルの形・ドラッグがそのまま働く。
★ 窓の手続きの中から Tk を呼ばないこと（Tk がメッセージを配っている最中）。PostMessage だけにする。
ファイルのドロップは OS が親の窓をたどるので、ここでは何もしない（app._setup_file_drop が本体の窓で受ける）。

どれかが失敗したら False を返す。呼び手（Paper）は行ごとに貼る形のまま動く。
"""
import sys

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CLIPSIBLINGS = 0x04000000
WS_EX_LAYERED = 0x00080000
LWA_COLORKEY = 1
RDW_INVALIDATE, RDW_ERASE, RDW_ALLCHILDREN, RDW_UPDATENOW = 0x1, 0x4, 0x80, 0x100
WM_NCDESTROY = 0x0082
# WM_MOUSEMOVE から WM_MBUTTONDBLCLK、WM_MOUSEWHEEL、WM_XBUTTON*、WM_MOUSEHWHEEL
MOUSE_MESSAGES = frozenset(range(0x0200, 0x020F))
SUBCLASS_ID = 0x434E    # 'CN'

_api = None
_proc = None


def available(version=None, platform=None):
    """この環境で透かしが使えそうか。"""
    if (platform or sys.platform) != 'win32':
        return False
    version = version or sys.getwindowsversion()
    return tuple(version[:2]) >= (6, 2)


def _load():
    """ctypes の準備。使えなければ None。"""
    global _api, _proc
    if _api is not None:
        return _api
    try:
        import ctypes
        import ctypes.wintypes as wt
        LRESULT = ctypes.c_ssize_t
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        comctl = ctypes.WinDLL('comctl32')
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_ssize_t)
        user32.SetLayeredWindowAttributes.restype = wt.BOOL
        user32.SetLayeredWindowAttributes.argtypes = (wt.HWND, wt.COLORREF, ctypes.c_ubyte, wt.DWORD)
        user32.RedrawWindow.restype = wt.BOOL
        user32.RedrawWindow.argtypes = (wt.HWND, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)
        user32.PostMessageW.restype = wt.BOOL
        user32.PostMessageW.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        SUBCLASSPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                          ctypes.c_size_t, ctypes.c_size_t)
        comctl.SetWindowSubclass.restype = wt.BOOL
        comctl.SetWindowSubclass.argtypes = (wt.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t)
        comctl.RemoveWindowSubclass.restype = wt.BOOL
        comctl.RemoveWindowSubclass.argtypes = (wt.HWND, SUBCLASSPROC, ctypes.c_size_t)
        comctl.DefSubclassProc.restype = LRESULT
        comctl.DefSubclassProc.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

        def forward(hwnd, msg, wparam, lparam, uid, target):
            # ★ Tk を呼ばない
            if msg in MOUSE_MESSAGES:
                user32.PostMessageW(target, msg, wparam, lparam)
                return 0
            if msg == WM_NCDESTROY:
                comctl.RemoveWindowSubclass(hwnd, _proc, SUBCLASS_ID)
            return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)

        _proc = SUBCLASSPROC(forward)
        _api = (ctypes, user32, comctl)
    except Exception:
        _api = None
        _proc = None
    return _api


def colorref(rgb16):
    """winfo_rgb の (r, g, b)（0〜65535）を COLORREF に。"""
    r, g, b = rgb16
    return (r >> 8) | ((g >> 8) << 8) | ((b >> 8) << 16)


def show_through(text_hwnd, key):
    """本文の欄の地の色（COLORREF）を透かす。色が変わった時も呼ぶ。"""
    api = _load()
    if api is None or not text_hwnd:
        return False
    _ctypes, user32, _comctl = api
    try:
        style = user32.GetWindowLongPtrW(text_hwnd, GWL_EXSTYLE)
        if not style & WS_EX_LAYERED:
            user32.SetWindowLongPtrW(text_hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            if not user32.GetWindowLongPtrW(text_hwnd, GWL_EXSTYLE) & WS_EX_LAYERED:
                return False
        if not user32.SetLayeredWindowAttributes(text_hwnd, key, 0, LWA_COLORKEY):
            user32.SetWindowLongPtrW(text_hwnd, GWL_EXSTYLE, style & ~WS_EX_LAYERED)
            return False
        return True
    except Exception:
        return False


def stop_showing_through(text_hwnd):
    """透かしをやめて、ふつうの窓に戻す。"""
    api = _load()
    if api is None or not text_hwnd:
        return
    _ctypes, user32, _comctl = api
    try:
        style = user32.GetWindowLongPtrW(text_hwnd, GWL_EXSTYLE)
        if style & WS_EX_LAYERED:
            user32.SetWindowLongPtrW(text_hwnd, GWL_EXSTYLE, style & ~WS_EX_LAYERED)
        repaint(text_hwnd)
    except Exception:
        pass


def attach_back(back_hwnd, text_hwnd):
    """後ろの Canvas の窓: 本文の欄と重なっていても絵を描ける形にして、マウスの操作を本文の欄へ送る。"""
    api = _load()
    if api is None or not back_hwnd or not text_hwnd:
        return False
    _ctypes, user32, comctl = api
    try:
        if not comctl.SetWindowSubclass(back_hwnd, _proc, SUBCLASS_ID, text_hwnd):
            return False
        # Tk の窓は兄弟と重なる所を描かない（WS_CLIPSIBLINGS）。残すと後ろが塗られず、真っ黒に透けて見える
        style = user32.GetWindowLongPtrW(back_hwnd, GWL_STYLE)
        user32.SetWindowLongPtrW(back_hwnd, GWL_STYLE, style & ~WS_CLIPSIBLINGS)
        return True
    except Exception:
        return False


def detach_back(back_hwnd):
    api = _load()
    if api is None or not back_hwnd:
        return
    _ctypes, _user32, comctl = api
    try:
        comctl.RemoveWindowSubclass(back_hwnd, _proc, SUBCLASS_ID)
    except Exception:
        pass


def repaint(hwnd):
    """窓とその子を描き直させる（透かしを始めた直後は、描き直すまで前の中身が出ない）。"""
    api = _load()
    if api is None or not hwnd:
        return
    try:
        api[1].RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW)
    except Exception:
        pass
