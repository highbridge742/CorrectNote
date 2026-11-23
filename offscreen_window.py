# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""試験の窓を、どの画面の置き方でも見えない所に置く（試験だけが使う。アプリは使わない）。

うにさんの決まり「試しの窓は画面の外で開く」。この PC では '+-4000+40' を指定しても、窓を出した時に Tk が窓を
画面の中（縦長の画面）へ寄せ直し、試験の窓がうにさんの画面に出ていた（2026-11-21）。
・hold(root, size): 窓を透明（-alpha 0）にしてから、全部の画面を合わせた範囲（仮想画面）の左の外へ
  SetWindowPos で置く。出してから（Tk が寄せ直した後に）もう一度置き、実際の位置を確かめる
・その後も、窓の大きさ・位置が変わるたびに（<Configure>）と、WATCH_MS ごとに確かめ、画面に掛かっていれば外へ置き直す
・透明のままにしておく（置き直すまでの一瞬に画面へ出ても見えない）
・試験の中で焦点を奪わない（2026-11-21 14:3xZ）: 試験の focus_force() は OS の焦点（前に出ている窓）まで試験の窓へ
  移していた。見えない窓が焦点を取ると、うにさんがその時に打った字が試験の窓へ入り（tests_f5_predict で行頭に ':' が
  入って落ちた）、うにさんの打った字も失われる。hold を呼んだ試験の中では、focus_force は試験のアプリの中の焦点だけを
  移し（Tk の focus）、focus_get は試験のアプリの中で焦点のある部品を返す（OS の焦点が無くても）
Windows 以外は '+-4000+40' を付けて geometry を呼ぶだけ。
"""
import sys

WATCH_MS = 250
GAP = 400


def _user32():
    import ctypes
    return ctypes.windll.user32


def _hwnd(root):
    u = _user32()
    wid = int(root.winfo_id())
    return u.GetParent(wid) or wid


def _rect(root):
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    _user32().GetWindowRect(_hwnd(root), ctypes.byref(r))
    return r


def on_a_screen(root):
    """窓が、どれかの画面に少しでも掛かっているか。"""
    if sys.platform != 'win32':
        return False
    import ctypes
    r = _rect(root)
    return bool(_user32().MonitorFromRect(ctypes.byref(r), 0))      # MONITOR_DEFAULTTONULL


def outside_point(root):
    """仮想画面（全部の画面を合わせた範囲）の左の外の位置。"""
    u = _user32()
    vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)          # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    r = _rect(root)
    width = max(1, r.right - r.left, int(root.winfo_reqwidth()))
    return vx - width - GAP, vy + 40


def _put_outside(root):
    x, y = outside_point(root)
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
    _user32().SetWindowPos(_hwnd(root), 0, int(x), int(y), 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)


def check(root):
    """画面に掛かっていれば外へ置き直す。置き直したら True。"""
    try:
        if not int(root.winfo_exists()) or not on_a_screen(root):
            return False
        _put_outside(root)
        return True
    except Exception:
        return False


_FOCUS_GUARDED = False


def real_focus_allowed(environ=None):
    """本当に窓を前へ出す試験（SetForegroundWindow で前の窓を替えて確かめる試験）を回してよいか。うにさんが PC を
    使っていない時に CN_TEST_REAL_FOCUS=1 で回す。既定では回さない（前へ出せない時と同じく、その試験は飛ばす）。"""
    import os
    environ = os.environ if environ is None else environ
    return environ.get('CN_TEST_REAL_FOCUS') == '1'


def guard_focus():
    """試験のファイルの頭で呼ぶ: この試験の中では OS の焦点を奪わない（hold の中でも呼ぶ）。"""
    _guard_focus()


def _guard_focus():
    """この試験の中では、OS の焦点を奪わない（focus_force → Tk の中だけ・focus_get → Tk の中の焦点）。"""
    global _FOCUS_GUARDED
    if _FOCUS_GUARDED or real_focus_allowed():
        return
    _FOCUS_GUARDED = True
    import tkinter
    real_get = tkinter.Misc.focus_get

    def focus_force(self):
        self.tk.call('focus', self._w)

    def focus_get(self):
        got = None
        try:
            got = real_get(self)
        except Exception:
            got = None
        if got is not None:
            return got
        try:
            name = str(self.tk.call('focus', '-lastfor', self._w))
            if name:
                return self._nametowidget(name)
        except Exception:
            pass
        return None
    tkinter.Misc.focus_force = focus_force
    tkinter.Misc.focus_get = focus_get


def hold(root, size=None):
    """root を見えない所に置き、そこに留める。size は 'WxH'（省略で今の大きさ）。"""
    _guard_focus()
    if sys.platform != 'win32':
        root.geometry((size or '') + '+-4000+40')
        return
    try:
        root.attributes('-alpha', 0.0)          # 置き直すまでの一瞬に画面へ寄せられても見えない
    except Exception:
        pass
    if size:
        root.geometry(size)
    root.update_idletasks()
    _put_outside(root)
    try:
        if str(root.state()) == 'withdrawn':
            root.deiconify()
    except Exception:
        pass
    root.update()                               # Tk はここで画面の中へ寄せ直すことがある
    _put_outside(root)
    root.update_idletasks()
    if not getattr(root, '_cn_offscreen_held', False):
        root._cn_offscreen_held = True
        root.bind('<Configure>', lambda e: check(root) if e.widget is root else None, add='+')

        def watch():
            if check(root) is None:
                return
            try:
                root.after(WATCH_MS, watch)
            except Exception:
                pass
        root.after(WATCH_MS, watch)
    check(root)
