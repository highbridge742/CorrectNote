# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""外の窓（ブラウザなど）からドラッグした文字を、メモ欄・補正欄・簡易入力の欄に落として取り込む（2026-11-21 17:20Z うにさん
「ブラウザの文字をドラッグして、アプリ本体か簡易入力にドロップしたら、取り込む」）。

drag_out.py と同じく、Windows の OLE（RegisterDragDrop・IDropTarget）を ctypes だけで作る（新しい部品は入れない）。
・受け取るのは文字だけ（CF_UNICODETEXT、無ければ CF_TEXT）。ファイル（CF_HDROP）は今まで通り開く（app の受け皿 _drop_queue へ
  道を積む。今までの WM_DROPFILES と同じ扱い）。画像などは受けない。クリップボードは触らない
・★★ OLE の手続き（DragEnter・DragOver・Drop）は Tk がメッセージを配っている最中に呼ばれるので、そこから Tk を呼ばない
  （ファイルのドロップと同じ・呼ぶとアプリごと落ちる）。手続きは受け皿に積むだけ。取り出し（落とす所の表示・字を入れる）は
  app の時計（_drain_drop_queue）が、ふつうのイベントとして行う。ドラッグが上に来ている間と、左のボタンが押されている間は、
  時計を速める（POLL_FAST_MS）。ふだんは1秒ごとなので、ドラッグの始めから落とす所が見えるまで最長およそ1秒
・落とした所に入れる。補正欄に落とした時は、メモ欄の同じ行・同じ位置へ（行より長ければ行の末尾）。1回の「元に戻す」で戻る。
  改行・タブ・全角空白はそのまま。入れた後は打った時と同じく補正と解析が走る
CN_DROP_IN_TEXT=0 で使わない（前の形）。
"""
import ctypes
import os
import sys
from ctypes import wintypes as W

from drag_out import (_Com, _guid, _proto, FORMATETC, STGMEDIUM, HRESULT, S_OK, CF_TEXT, CF_UNICODETEXT, TYMED_HGLOBAL,
                      DROPEFFECT_NONE, DROPEFFECT_COPY)

CF_HDROP = 15
POLL_FAST_MS = 50


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return sys.platform == 'win32' and environ.get('CN_DROP_IN_TEXT') != '0'


_GetData = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM))
_QueryGetData = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC))


def _method(obj, index, proto):
    vtbl = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    return proto(vtbl[index])


def _fmt(cf):
    return FORMATETC(cf, None, 1, -1, TYMED_HGLOBAL)


def has_format(data, cf):
    try:
        f = _fmt(cf)
        return _method(data, 5, _QueryGetData)(data, ctypes.byref(f)) == S_OK
    except Exception:
        return False


def _kernel():
    k = ctypes.windll.kernel32
    k.GlobalLock.argtypes = [ctypes.c_void_p]; k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k.GlobalSize.argtypes = [ctypes.c_void_p]; k.GlobalSize.restype = ctypes.c_size_t
    return k


def _release(medium):
    try:
        ole = ctypes.windll.ole32
        ole.ReleaseStgMedium.argtypes = [ctypes.POINTER(STGMEDIUM)]
        ole.ReleaseStgMedium(ctypes.byref(medium))
    except Exception:
        pass


def read_text(data):
    """IDataObject から文字（CF_UNICODETEXT、無ければ CF_TEXT）。無ければ None。"""
    for cf in (CF_UNICODETEXT, CF_TEXT):
        if not has_format(data, cf):
            continue
        f = _fmt(cf)
        medium = STGMEDIUM()
        try:
            if _method(data, 3, _GetData)(data, ctypes.byref(f), ctypes.byref(medium)) != S_OK or not medium.hGlobal:
                continue
        except Exception:
            continue
        try:
            k = _kernel()
            p = k.GlobalLock(medium.hGlobal)
            if not p:
                continue
            try:
                size = k.GlobalSize(medium.hGlobal)
                raw = ctypes.string_at(p, size)
            finally:
                k.GlobalUnlock(medium.hGlobal)
            if cf == CF_UNICODETEXT:
                text = raw.decode('utf-16-le', 'replace')
            else:
                text = raw.decode('mbcs', 'replace')
            return text.split('\x00', 1)[0]
        finally:
            _release(medium)
    return None


def read_files(data):
    """IDataObject からファイルの道（CF_HDROP）。無ければ []。"""
    if not has_format(data, CF_HDROP):
        return []
    f = _fmt(CF_HDROP)
    medium = STGMEDIUM()
    try:
        if _method(data, 3, _GetData)(data, ctypes.byref(f), ctypes.byref(medium)) != S_OK or not medium.hGlobal:
            return []
    except Exception:
        return []
    out = []
    try:
        sh = ctypes.windll.shell32
        sh.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
        sh.DragQueryFileW.restype = ctypes.c_uint
        n = sh.DragQueryFileW(medium.hGlobal, 0xFFFFFFFF, None, 0)
        for i in range(n):
            need = sh.DragQueryFileW(medium.hGlobal, i, None, 0)
            buf = ctypes.create_unicode_buffer(need + 1)
            if sh.DragQueryFileW(medium.hGlobal, i, buf, need + 1):
                out.append(buf.value)
    except Exception:
        pass
    finally:
        _release(medium)
    return out


def _point(value):
    """POINTL（値渡しの 8 バイト）→ (x, y)。"""
    v = int(value) & 0xFFFFFFFFFFFFFFFF
    x = v & 0xFFFFFFFF
    y = (v >> 32) & 0xFFFFFFFF
    return (x - (1 << 32) if x & 0x80000000 else x, y - (1 << 32) if y & 0x80000000 else y)


class DropTarget(_Com):
    """IDropTarget。手続きは state（受け皿）に積むだけ（Tk を呼ばない）。"""

    def __init__(self, name, state):
        self.IIDS = (_guid('00000122-0000-0000-C000-000000000046'),)
        self.name = name              # どの欄か（'editor'・'result'・'quick'）
        self.state = state            # app が持つ受け皿: {'over': (name, x, y) or None, 'drops': [...], 'files': list}
        self.kind = None
        P = ctypes.c_int64
        methods = [_proto(ctypes.c_void_p, W.DWORD, P, ctypes.POINTER(W.DWORD))(self._enter),
                   _proto(W.DWORD, P, ctypes.POINTER(W.DWORD))(self._over),
                   _proto()(self._leave),
                   _proto(ctypes.c_void_p, W.DWORD, P, ctypes.POINTER(W.DWORD))(self._drop)]
        super().__init__(methods)

    @staticmethod
    def _effect(peffect, value):
        try:
            if peffect:
                peffect[0] = value
        except Exception:
            pass

    def _enter(self, this, data, keys, pt, peffect):
        try:
            if has_format(data, CF_UNICODETEXT) or has_format(data, CF_TEXT):
                self.kind = 'text'
            elif has_format(data, CF_HDROP):
                self.kind = 'files'
            else:
                self.kind = None
        except Exception:
            self.kind = None
        if self.kind == 'text':
            x, y = _point(pt)
            self.state['over'] = (self.name, x, y)
        self._effect(peffect, DROPEFFECT_COPY if self.kind else DROPEFFECT_NONE)
        return S_OK

    def _over(self, this, keys, pt, peffect):
        if self.kind == 'text':
            x, y = _point(pt)
            self.state['over'] = (self.name, x, y)
        self._effect(peffect, DROPEFFECT_COPY if self.kind else DROPEFFECT_NONE)
        return S_OK

    def _leave(self, this):
        self.kind = None
        self.state['over'] = None
        self.state['left'] = True
        return S_OK

    def _drop(self, this, data, keys, pt, peffect):
        kind, self.kind = self.kind, None
        self.state['over'] = None
        effect = DROPEFFECT_NONE
        try:
            if kind == 'text':
                text = read_text(data)
                if text:
                    x, y = _point(pt)
                    self.state['drops'].append((self.name, x, y, text))
                    effect = DROPEFFECT_COPY
            elif kind == 'files':
                paths = read_files(data)
                if paths:
                    self.state['files'].append(paths)
                    effect = DROPEFFECT_COPY
        except Exception:
            effect = DROPEFFECT_NONE
        self._effect(peffect, effect)
        return S_OK


def register(hwnd, target):
    """RegisterDragDrop。できたら True。"""
    if not enabled() or not hwnd:
        return False
    try:
        ole = ctypes.windll.ole32
        ole.OleInitialize(None)
        ole.RegisterDragDrop.argtypes = [W.HWND, ctypes.c_void_p]
        ole.RegisterDragDrop.restype = HRESULT
        return ole.RegisterDragDrop(W.HWND(hwnd), target.pointer) == S_OK
    except Exception:
        return False


def revoke(hwnd):
    try:
        ole = ctypes.windll.ole32
        ole.RevokeDragDrop.argtypes = [W.HWND]
        ole.RevokeDragDrop(W.HWND(hwnd))
    except Exception:
        pass


# --- Tk の側（app の時計の中から呼ぶ。ここは Tk を呼んでよい） -------------------------------------------------------
def _widget(app, name):
    if name == 'quick':
        return getattr(app, '_quick_text', None)
    if name == 'result':
        return getattr(app, 'result_view', None)
    return getattr(app, 'editor', None)


def _index_at(widget, x, y):
    return widget.index('@%d,%d' % (x - widget.winfo_rootx(), y - widget.winfo_rooty()))


def _target(app, name, x, y):
    """(入れる欄, 位置)。補正欄なら、メモ欄の同じ行・同じ位置（行より長ければ行の末尾）。"""
    w = _widget(app, name)
    if w is None:
        return None, None
    try:
        index = _index_at(w, x, y)
    except Exception:
        return None, None
    if name != 'result':
        return w, index
    ed = getattr(app, 'editor', None)
    if ed is None:
        return None, None
    try:
        row, col = (int(v) for v in str(index).split('.'))
        line = ed.get('%d.0' % row, '%d.end' % row)
        return ed, '%d.%d' % (row, min(col, len(line)))
    except Exception:
        return None, None


def show_over(app, state):
    """ドラッグが上に来ている間: 落とす所にカーソルを置いて、動かした時の色で点滅させずに見せる。"""
    over = state.get('over')
    if over is None:
        if state.pop('left', False):
            hide_over(app, state)
        return
    name, x, y = over
    w, index = _target(app, name, x, y)
    if w is None:
        return
    try:
        if 'saved' not in state:
            state['saved'] = (w, str(w.index('insert')), str(w.cget('insertbackground')), int(w.cget('insertofftime')))
            try:
                import editor_guides
                color = editor_guides.FLASH_COLOR
            except Exception:
                color = '#ee963e'
            w.configure(insertbackground=color, insertofftime=0)
        w.mark_set('insert', index)
        w.see(index)
    except Exception:
        pass


def hide_over(app, state, keep_insert=False):
    saved = state.pop('saved', None)
    if saved is None:
        return
    w, insert, background, off = saved
    try:
        if not keep_insert:
            w.mark_set('insert', insert)
        w.configure(insertbackground=background, insertofftime=off)
    except Exception:
        pass


def take_drop(app, name, x, y, text):
    """落とした字を入れる。入れたら True。"""
    w, index = _target(app, name, x, y)
    if w is None or not text:
        return False
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    try:
        state = str(w.cget('state'))
        if state != 'normal':
            return False
        from text_edit import undo_group
        mark = 'cn_drop_in'
        w.mark_set(mark, index)
        w.mark_gravity(mark, 'left')
        with undo_group(w):                 # 1回の「元に戻す」で戻る
            w.insert(mark, text)
        end = str(w.index('%s +%dc' % (mark, len(text))))
        w.mark_unset(mark)
        w.mark_set('insert', end)
        w.see('insert')
        try:
            w.focus_set()
        except Exception:
            pass
    except Exception:
        return False
    try:
        if w is getattr(app, 'editor', None):
            app._on_change()                # 打った時と同じく補正と解析が走る
        else:
            changed = getattr(app, '_on_quick_change', None)
            if changed is not None:
                changed()
    except Exception:
        pass
    return True


def drain(app, state):
    """時計から: 落とす所の表示と、落とした字の取り込み。速めるべきなら True。"""
    drops = state.get('drops') or []
    if drops:
        hide_over(app, state, keep_insert=True)
    while drops:
        name, x, y, text = drops.pop(0)
        take_drop(app, name, x, y, text)
    files = state.get('files') or []
    while files:
        try:
            app._drop_queue.append(files.pop(0))        # 今までのファイルのドロップと同じ道
        except Exception:
            files.clear()
    show_over(app, state)
    return state.get('over') is not None or _left_button_down()


def _left_button_down():
    """左のボタンが押されているか（ドラッグは押して始まる。押されている間は時計を速めて、外からのドラッグが上に来たのを
    すぐ見る）。OLE の手続きからは時計を速められない（Tk を呼べない）ので、時計の側で見る。"""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:
        return False
