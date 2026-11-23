# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""選んだ範囲のドラッグを、アプリの窓の外の入力欄へ落とす（2026-11-20 うにさん「長押しの単語移動は、アプリ外の
入力欄にドロップできるようにする。この場合は複製として元の文字を残す」）。

Windows の OLE のドラッグ（DoDragDrop）を ctypes だけで行う（pywin32 などの新しい部品は使わない。EXE の同梱も変わらない）。
渡すのは CF_UNICODETEXT と CF_TEXT の文字だけ、効果は DROPEFFECT_COPY だけ（外へ落としても元の字は残す）。
クリップボードは使わない（触らない）。
・drag_move が、ドラッグ中に指がアプリの窓の外へ出たらここを呼ぶ。外で離すと、その欄が字を受け取る
・Esc・落とせない所で離した時は取りやめ。外へ出た後に窓の中へ戻った時も、OLE の方は取りやめ、アプリの中の移動の
  続きに戻る（戻り値 'back'）
・OLE の手続き（QueryContinueDrag など）の中からは Tk を呼ばない（OLE が窓の知らせを配っている最中）
CN_DRAG_OUT=0 で使わない（前の形）。
"""
import ctypes
import os
import sys
from ctypes import wintypes as W

S_OK = 0
S_FALSE = 1
E_NOINTERFACE = 0x80004002 - 0x100000000
E_NOTIMPL = 0x80004001 - 0x100000000
DV_E_FORMATETC = 0x80040064 - 0x100000000
OLE_E_ADVISENOTSUPPORTED = 0x80040003 - 0x100000000
DRAGDROP_S_DROP = 0x00040100
DRAGDROP_S_CANCEL = 0x00040101
DRAGDROP_S_USEDEFAULTCURSORS = 0x00040102
DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1
CF_TEXT = 1
CF_UNICODETEXT = 13
TYMED_HGLOBAL = 1
DATADIR_GET = 1
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
GMEM_MOVEABLE = 0x0002

HRESULT = ctypes.c_long


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return sys.platform == 'win32' and environ.get('CN_DRAG_OUT') != '0'


class GUID(ctypes.Structure):
    _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD), ('Data3', W.WORD), ('Data4', ctypes.c_ubyte * 8)]


def _guid(text):
    g = GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p('{%s}' % text), ctypes.byref(g)) if sys.platform == 'win32' else None
    return bytes(g)


class FORMATETC(ctypes.Structure):
    _fields_ = [('cfFormat', W.WORD), ('ptd', ctypes.c_void_p), ('dwAspect', W.DWORD), ('lindex', W.LONG),
                ('tymed', W.DWORD)]


class STGMEDIUM(ctypes.Structure):
    _fields_ = [('tymed', W.DWORD), ('hGlobal', ctypes.c_void_p), ('pUnkForRelease', ctypes.c_void_p)]


def _proto(*args):
    return ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *args)


_ULONG = ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)
_QI = _proto(ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))


class _Com:
    """ctypes で作る COM の物の土台（vtable と参照の数）。Python 側で持ち続け、DoDragDrop の間は消えない。"""
    IIDS = ()

    def __init__(self, methods):
        self._refs = 1
        funcs = [_QI(self._qi), _ULONG(self._addref), _ULONG(self._release)] + methods
        self._funcs = funcs
        self._vtbl = (ctypes.c_void_p * len(funcs))(*[ctypes.cast(f, ctypes.c_void_p) for f in funcs])
        self._obj = (ctypes.c_void_p * 1)(ctypes.addressof(self._vtbl))
        self.pointer = ctypes.addressof(self._obj)
        self._iids = set(self.IIDS) | {_guid('00000000-0000-0000-C000-000000000046')}

    def _qi(self, this, riid, ppv):
        try:
            iid = ctypes.string_at(riid, 16)
        except Exception:
            iid = b''
        if iid in self._iids:
            ppv[0] = self.pointer
            self._refs += 1
            return S_OK
        ppv[0] = None
        return E_NOINTERFACE

    def _addref(self, this):
        self._refs += 1
        return self._refs

    def _release(self, this):
        self._refs = max(0, self._refs - 1)
        return self._refs


class DataObject(_Com):
    """IDataObject: 文字（CF_UNICODETEXT・CF_TEXT）だけを渡す。"""

    def __init__(self, text):
        self.IIDS = (_guid('0000010E-0000-0000-C000-000000000046'),)
        self.text = text
        self.asked = []
        methods = [
            _proto(ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM))(self._get_data),
            _proto(ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM))(lambda this, f, m: E_NOTIMPL),
            _proto(ctypes.POINTER(FORMATETC))(self._query),
            _proto(ctypes.POINTER(FORMATETC), ctypes.POINTER(FORMATETC))(lambda this, a, b: E_NOTIMPL),
            _proto(ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM), W.BOOL)(lambda this, f, m, r: E_NOTIMPL),
            _proto(W.DWORD, ctypes.POINTER(ctypes.c_void_p))(self._enum),
            _proto(ctypes.POINTER(FORMATETC), W.DWORD, ctypes.c_void_p, ctypes.POINTER(W.DWORD))(
                lambda this, f, a, s, c: OLE_E_ADVISENOTSUPPORTED),
            _proto(W.DWORD)(lambda this, c: OLE_E_ADVISENOTSUPPORTED),
            _proto(ctypes.POINTER(ctypes.c_void_p))(lambda this, p: OLE_E_ADVISENOTSUPPORTED),
        ]
        super().__init__(methods)

    def payload(self, cf):
        if cf == CF_UNICODETEXT:
            return self.text.encode('utf-16-le', 'surrogatepass') + b'\0\0'
        if cf == CF_TEXT:
            return self.text.encode('mbcs', 'replace') + b'\0'
        return None

    def _ok(self, fmt):
        try:
            f = fmt.contents
        except ValueError:
            return False
        return f.cfFormat in (CF_UNICODETEXT, CF_TEXT) and bool(f.tymed & TYMED_HGLOBAL)

    def _query(self, this, fmt):
        return S_OK if self._ok(fmt) else DV_E_FORMATETC

    def _get_data(self, this, fmt, medium):
        if not self._ok(fmt):
            return DV_E_FORMATETC
        data = self.payload(fmt.contents.cfFormat)
        self.asked.append(fmt.contents.cfFormat)
        k32 = ctypes.windll.kernel32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return E_NOTIMPL
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        medium.contents.tymed = TYMED_HGLOBAL
        medium.contents.hGlobal = h
        medium.contents.pUnkForRelease = None
        return S_OK

    def _enum(self, this, direction, out):
        if direction != DATADIR_GET:
            return E_NOTIMPL
        formats = (FORMATETC * 2)(FORMATETC(CF_UNICODETEXT, None, 1, -1, TYMED_HGLOBAL),
                                  FORMATETC(CF_TEXT, None, 1, -1, TYMED_HGLOBAL))
        shell = ctypes.windll.shell32
        shell.SHCreateStdEnumFmtEtc.argtypes = [W.UINT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        return shell.SHCreateStdEnumFmtEtc(2, formats, out)


class DropSource(_Com):
    """IDropSource: Esc で取りやめ・左を離したら落とす・窓の中へ戻ったら OLE の方は取りやめ（'back'）。"""

    def __init__(self, inside=None):
        self.IIDS = (_guid('00000121-0000-0000-C000-000000000046'),)
        self.inside = inside          # 指の画面の位置 → アプリの窓の中か（Tk を呼ばない関数）
        self.back = False
        self.cancelled = False
        methods = [_proto(W.BOOL, W.DWORD)(self._continue), _proto(W.DWORD)(lambda this, e: DRAGDROP_S_USEDEFAULTCURSORS)]
        super().__init__(methods)

    def _continue(self, this, escape, keys):
        if escape:
            self.cancelled = True
            return DRAGDROP_S_CANCEL
        # 窓の中なら OLE の方は取りやめ（アプリの中の移動へ戻す）。離したのが窓の中でも同じ（drag_move が中で落とす）
        if self.inside is not None:
            pt = W.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            if self.inside(pt.x, pt.y):
                self.back = True
                return DRAGDROP_S_CANCEL
        if not keys & MK_LBUTTON:
            return DRAGDROP_S_DROP
        return S_OK


def drag_text_out(text, inside=None, dodragdrop=None):
    """text を外へドラッグする。戻り値: 'dropped'（外の欄が受け取った）・'back'（窓の中へ戻った）・'cancelled'。"""
    if not text or not enabled():
        return 'cancelled'
    data = DataObject(text)
    source = DropSource(inside)
    effect = W.DWORD(0)
    if dodragdrop is None:
        ole = ctypes.oledll.ole32 if False else ctypes.windll.ole32
        ole.OleInitialize(None)
        ole.DoDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)]
        ole.DoDragDrop.restype = HRESULT
        dodragdrop = ole.DoDragDrop
    hr = dodragdrop(data.pointer, source.pointer, DROPEFFECT_COPY, ctypes.byref(effect))
    if source.back:
        return 'back'
    if hr == DRAGDROP_S_DROP and effect.value & DROPEFFECT_COPY:
        return 'dropped'
    return 'cancelled'
