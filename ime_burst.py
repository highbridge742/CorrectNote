# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""IME の確定1回の字をまとめる（2026-11-05 うにさん「確定した文字列が1字ずつ左から順に出る」）。

Windows の Tk は確定した文字列を1字ずつのキーとして渡す。そのたびに _on_change が走ると、
先頭の強制描画で1字ずつ画面に出て、行番号・塗り直しの段取りも字数ぶん回る。
確定した文字列は IME から分かるので、カーソルの前がその文字列になるまで待ち、最後の字で1回だけ行う。
来ない字があっても WAIT_MS で必ず行う。

確定の知らせ（WM_IME_COMPOSITION）は、Tk がキーの入力先にした窓（メモ欄の欄ではなく、その上の窓）に届く。
本物の IME と SendInput で確かめた。Tk を呼ばず、IME の状態も変えず、読むだけ。

簡易入力も同じ形（窓は簡易入力の窓・欄は簡易入力の欄）。

確定でない普通の打鍵はここを通らず今までどおり。語を拾う・括弧・F2 の最中は、字ごとに見る意味があるので
まとめない（「＝」の字も同じ）。打鍵の記録（stroke_keys・_on_editor_typed）は別の束縛なので字ごとのまま。"""
import sys
import time

WAIT_MS = 120
MAX_AGE_S = 1.0     # メモ欄へ来なかった確定（検索欄など）が、その後の打鍵を待たせないように
WM_IME_COMPOSITION = 0x010F
WM_NCDESTROY = 0x0082
GCS_RESULTSTR = 0x0800


class Watch:
    """Tk のキーの入力先の窓で、確定した文字列を覚える。"""
    def __init__(self, hwnd):
        self.hwnd = 0
        self._arriving = None
        self._at = 0.0
        self._proc = None
        if sys.platform != 'win32' or not hwnd:
            return
        import ctypes as C
        from ctypes import wintypes as W
        self._uid = id(self)
        self._type = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, C.c_size_t, C.c_ssize_t, C.c_size_t, C.c_size_t)
        dll = self._dll = C.WinDLL('comctl32')
        dll.SetWindowSubclass.argtypes = [W.HWND, self._type, C.c_size_t, C.c_size_t]
        dll.SetWindowSubclass.restype = W.BOOL
        dll.RemoveWindowSubclass.argtypes = [W.HWND, self._type, C.c_size_t]
        dll.RemoveWindowSubclass.restype = W.BOOL
        dll.DefSubclassProc.argtypes = [W.HWND, W.UINT, C.c_size_t, C.c_ssize_t]
        dll.DefSubclassProc.restype = C.c_ssize_t
        self._proc = self._type(self._message)
        if dll.SetWindowSubclass(hwnd, self._proc, self._uid, 0):
            self.hwnd = hwnd

    @property
    def arriving(self):
        if self._arriving and time.monotonic() - self._at > MAX_AGE_S:
            self._arriving = None
        return self._arriving

    @arriving.setter
    def arriving(self, value):
        self._arriving = value

    def _message(self, hwnd, message, wparam, lparam, uid, ref):
        try:
            if message == WM_IME_COMPOSITION and lparam & GCS_RESULTSTR:
                from ime_watch import read_composition
                self.arriving = (read_composition(hwnd) or {}).get('result') or None
                self._at = time.monotonic()
            elif message == WM_NCDESTROY:
                self.close()
        except Exception:
            pass
        return self._dll.DefSubclassProc(hwnd, message, wparam, lparam)

    def close(self):
        # 外せなかった時は呼び先を残す（Windows が解放済みの所を呼ばないように）
        if self.hwnd and self._dll.RemoveWindowSubclass(self.hwnd, self._proc, self._uid):
            self.hwnd = 0
        self.arriving = None


def install(app):
    """本体の窓に見張りを付ける（一度だけ）。"""
    if getattr(app, '_ime_burst_watch', None) is not None:
        return
    try:
        app._ime_burst_watch = Watch(int(app.root.winfo_id()))
    except Exception:
        app._ime_burst_watch = None


def _special(app):
    return (getattr(app, '_pick_mode', None) or getattr(app, '_bracket_exit', None)
            or getattr(app, '_f2_focus_target', None) is not None)


def _cancel(app):
    job = getattr(app, '_ime_burst_job', None)
    app._ime_burst_job = None
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass


def install_quick(app, win):
    """簡易入力の窓に見張りを付ける（窓を開くたび。窓が消えると見張りも外れる）。"""
    try:
        app._quick_burst_watch = Watch(int(win.winfo_id()))
    except Exception:
        app._quick_burst_watch = None


def close_quick(app):
    """簡易入力を閉じる時。待っている後始末は行わない（欄が無い）。"""
    job = getattr(app, '_quick_burst_job', None)
    app._quick_burst_job = None
    app._quick_burst_event = None
    app._quick_burst_watch = None
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass


def hold_quick(app, event=None):
    """hold の簡易入力の欄の形。"""
    watch = getattr(app, '_quick_burst_watch', None)
    result = getattr(watch, 'arriving', None)
    text = getattr(app, '_quick_text', None)
    if not result or text is None:
        return False
    def cancel():
        job = getattr(app, '_quick_burst_job', None)
        app._quick_burst_job = None
        if job is not None:
            app.root.after_cancel(job)
    try:
        whole = len(result) < 2 or text.get(f'insert-{len(result)}c', 'insert') == result
        if whole or _special(app) or text.get('insert-1c', 'insert') in ('＝', '='):
            watch.arriving = None
            cancel()
            if whole:
                text.update_idletasks()
            return False
        cancel()
        app._quick_burst_job = app.root.after(WAIT_MS, lambda: _finish_quick(app))
    except Exception:
        watch.arriving = None
        return False
    app._quick_burst_event = event
    return True


def _finish_quick(app):
    app._quick_burst_job = None
    watch = getattr(app, '_quick_burst_watch', None)
    if watch is not None:
        watch.arriving = None
    event = getattr(app, '_quick_burst_event', None)
    app._quick_burst_event = None
    text = getattr(app, '_quick_text', None)
    if text is None:
        return
    try:
        text.update_idletasks()
    except Exception:
        pass
    app._on_quick_change(event)


def holding(app):
    """確定の字がまだ続けて来る途中か（描画の予約を見送る側が尋ねる）。"""
    watch = getattr(app, '_ime_burst_watch', None)
    return bool(getattr(watch, 'arriving', None))


def hold(app, event=None):
    """True: この字の後始末は確定の最後の字で行う。"""
    watch = getattr(app, '_ime_burst_watch', None)
    result = getattr(watch, 'arriving', None)
    if not result:
        return False
    try:
        whole = len(result) < 2 or app.editor.get(f'insert-{len(result)}c', 'insert') == result
        if whole or _special(app) or app.editor.get('insert-1c', 'insert') in ('＝', '='):
            watch.arriving = None
            _cancel(app)
            if whole:
                _draw(app)
            return False
        _cancel(app)
        app._ime_burst_job = app.root.after(WAIT_MS, lambda: _finish(app))
    except Exception:
        watch.arriving = None
        return False
    app._ime_burst_event = event
    return True


def _draw(app):
    # 解析の時計が続くと Tk は暇にならず描かない（draw_soon の 2026-10-18）。最後の字で1回だけ描く
    try:
        app.editor.update_idletasks()
    except Exception:
        pass


def _finish(app):
    app._ime_burst_job = None
    watch = getattr(app, '_ime_burst_watch', None)
    if watch is not None:
        watch.arriving = None
    event = getattr(app, '_ime_burst_event', None)
    app._ime_burst_event = None
    _draw(app)
    app._on_change(event)
