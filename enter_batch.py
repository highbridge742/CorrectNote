# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""エンターを押し続けて処理が遅れたとき、溜まったエンターの改行をまとめて入れる（2026-11-07 うにさん「処理が遅れたあと、
2回以上分の入力が来ていたなら、改行をまとめて複数個入れてはどうか」・見た目は変えない）。

1回の改行の重さの大半は、Tk が下の行を全部ずらして描き直す手間で、それは手が空いた時に1回まとめて走る。キーの知らせが
窓の待ち行列に溜まっていると、その知らせ1つごとに描き直しと後処理が走って追いつかない。

ここでは、本文の欄のエンター（Tk の Text の既定の束縛が改行を1つ入れた**後**）に、待ち行列の先頭に並んでいる
エンターの「押した」の知らせを取り出し、その数だけ、同じ既定の束縛と同じやり方（tk::TextInsert で改行1つ・
元に戻すの区切り1つ）で続けて入れる。入る字・カーソル・元に戻すの単位は1回ずつ押した時と同じで、描き直しと後処理が
1回にまとまる。

取り出すのは、待ち行列のキーの知らせの先頭が「修飾なしのエンターを押した」で、それより前に押されたマウスのボタンが
無い時だけ（ほかのキーやクリックが間に挟まれば、そこで止めて順番を崩さない）。変換中・Shift などを押している・
本文の欄にフォーカスが無い時は何もしない（今までどおり1回ずつ）。Windows 以外では何もしない。
"""
import sys

TAG = 'CorrectNoteEnterBatch'
MAX_BATCH = 64          # 一度に取り出す上限（それより多ければ次の回に）
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
WM_KEYFIRST, WM_KEYLAST = 0x0100, 0x0109
WM_MOUSEFIRST, WM_MOUSELAST = 0x0200, 0x020E
WM_MOUSEMOVE = 0x0200
VK_RETURN = 0x0D
PM_NOREMOVE, PM_REMOVE = 0x0000, 0x0001
_MODIFIERS = 0x0001 | 0x0004 | 0x20000     # Shift・Control・Alt（Windows の Tk。0x0008 は NumLock が立つことがある）

_api = None


def _user32():
    global _api
    if _api is None:
        import ctypes
        from ctypes import wintypes as W

        class MSG(ctypes.Structure):
            _fields_ = [('hwnd', W.HWND), ('message', W.UINT), ('wParam', W.WPARAM), ('lParam', W.LPARAM),
                        ('time', W.DWORD), ('pt', W.POINT)]
        user = ctypes.WinDLL('user32')
        user.PeekMessageW.argtypes = [ctypes.POINTER(MSG), W.HWND, W.UINT, W.UINT, W.UINT]
        user.PeekMessageW.restype = W.BOOL
        user.GetKeyState.argtypes = [ctypes.c_int]
        user.GetKeyState.restype = ctypes.c_short
        _api = (user, MSG, ctypes)
    return _api


def install(app, widget):
    """本文の欄の束縛の並びの、Tk の Text の既定の束縛のすぐ後ろに札を1枚足す。"""
    if sys.platform != 'win32':
        return False
    try:
        tags = list(widget.bindtags())
        if TAG in tags:
            return True
        at = tags.index('Text') + 1 if 'Text' in tags else 1
        tags.insert(at, TAG)
        # 先頭にもう1枚: この欄のエンターの知らせを1つずつ受け取り、元の Windows の知らせの回数を取り出す
        # （欄の束縛が 'break' を返しても、ここは先に通る）。フォーカスの出入りも見る（手続きは欄にある時だけ控える）
        tags.insert(0, TAG + 'Pre')
        widget.bindtags(tuple(tags))
        widget.bind_class(TAG, '<Return>', lambda event: on_return(app, event))
        widget.bind_class(TAG + 'Pre', '<Return>', lambda event: _take_own(app))
        widget.bind_class(TAG + 'Pre', '<FocusIn>', lambda event: _focus(app, True))
        widget.bind_class(TAG + 'Pre', '<FocusOut>', lambda event: _focus(app, False))
        app._enter_batch = dict(presses=0, batched=0, batches=0, largest=0, repeated=0)
        _watch_repeats(app, (app.root.winfo_id(), widget.winfo_id()))
        return True
    except Exception:
        return False


def _queued_return(user, MSG, ctypes):
    """待ち行列のキーの先頭が修飾なしのエンターの「押した」で、それより前にマウスのボタンが無ければ取り出して、その回数
    （自動の繰り返しの数）を返す。取り出さなければ 0。"""
    msg = MSG()
    if not user.PeekMessageW(ctypes.byref(msg), None, WM_KEYFIRST, WM_KEYLAST, PM_NOREMOVE):
        return 0
    if msg.message != WM_KEYDOWN or msg.wParam != VK_RETURN:
        return 0
    key_time = msg.time
    mouse = MSG()
    # マウスの知らせ（動きは除く）が、このキーより前に押されていたら止める
    if user.PeekMessageW(ctypes.byref(mouse), None, WM_MOUSEMOVE + 1, WM_MOUSELAST, PM_NOREMOVE):
        if ((mouse.time - key_time) & 0xffffffff) > 0x7fffffff or mouse.time == key_time:
            return 0
    taken = MSG()
    if not user.PeekMessageW(ctypes.byref(taken), None, WM_KEYDOWN, WM_KEYDOWN, PM_REMOVE):
        return 0
    if taken.wParam != VK_RETURN:
        return 0                    # 起きないはず（先頭を見たばかり）
    return max(1, int(taken.lParam) & 0xFFFF)     # 遅れている間の自動の繰り返しは、1つの知らせに回数で入っている


def _watch_repeats(app, hwnds):
    """本文の窓（キーの知らせが届く root の窓と欄）の手続きの前で、エンターの「押した」の回数（lParam の下16ビット）を
    控える。手続きの中では Tk を呼ばない（数を足すだけ）。"""
    import collections
    import ctypes as C
    from ctypes import wintypes as W
    app._enter_repeats = collections.deque(maxlen=64)
    kind = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, C.c_size_t, C.c_ssize_t, C.c_size_t, C.c_size_t)
    dll = C.WinDLL('comctl32')
    dll.SetWindowSubclass.argtypes = [W.HWND, kind, C.c_size_t, C.c_size_t]
    dll.SetWindowSubclass.restype = W.BOOL
    dll.DefSubclassProc.argtypes = [W.HWND, W.UINT, C.c_size_t, C.c_ssize_t]
    dll.DefSubclassProc.restype = C.c_ssize_t
    repeats = app._enter_repeats

    user = C.WinDLL('user32')
    user.GetMessageTime.restype = C.c_long

    def proc(hwnd, message, wparam, lparam, uid, ref):
        try:
            if message == WM_KEYDOWN and wparam == VK_RETURN and getattr(app, '_enter_focus', False):
                repeats.append(max(1, int(lparam) & 0xFFFF))
                stats = getattr(app, '_enter_batch', None)
                if stats is not None:
                    stats['raw'] = stats.get('raw', 0) + 1
                    stats['raw_repeats'] = stats.get('raw_repeats', 0) + (max(1, int(lparam) & 0xFFFF))
        except Exception:
            pass
        return dll.DefSubclassProc(hwnd, message, wparam, lparam)
    app._enter_repeat_proc = kind(proc)       # kept for the window's life
    for hwnd in hwnds:
        try:
            if hwnd:
                dll.SetWindowSubclass(hwnd, app._enter_repeat_proc, 0x454E5452, 0)
        except Exception:
            pass


def _focus(app, inside):
    app._enter_focus = inside
    if not inside:
        repeats = getattr(app, '_enter_repeats', None)
        if repeats is not None:
            repeats.clear()


def _take_own(app):
    """欄のエンターの知らせ1つに、Windows の知らせ1つ（届いた順）。回数を on_return へ渡す。"""
    repeats = getattr(app, '_enter_repeats', None)
    try:
        app._enter_own = repeats.popleft() if repeats else 1
    except Exception:
        app._enter_own = 1
    return None


def _own_repeat(app, event):
    own, app._enter_own = getattr(app, '_enter_own', 1), 1
    return own if isinstance(own, int) and own >= 1 else 1


def on_return(app, event):
    """既定の束縛が改行を1つ入れた後に呼ばれる。溜まっていたエンターの分を続けて入れる。"""
    stats = getattr(app, '_enter_batch', None)
    if stats is not None:
        stats['presses'] += 1
    widget = event.widget
    own = _own_repeat(app, event)
    try:
        if int(getattr(event, 'state', 0) or 0) & _MODIFIERS:
            stats and stats.__setitem__('skip_mod', stats.get('skip_mod', 0) + 1)
            return None
        if widget.focus_get() is not widget:
            stats and stats.__setitem__('skip_focus', stats.get('skip_focus', 0) + 1)
            return None
        try:
            import ime_watch
            if ime_watch.composition_live(widget.winfo_id()):
                stats and stats.__setitem__('skip_ime', stats.get('skip_ime', 0) + 1)
                return None
        except Exception:
            return None
        user, MSG, ctypes = _user32()
        for vk in (0x10, 0x11, 0x12):           # Shift・Ctrl・Alt が今押されていれば触らない
            if user.GetKeyState(vk) & 0x8000:
                stats and stats.__setitem__('skip_key', stats.get('skip_key', 0) + 1)
                return None
        # この知らせ自身の回数（Windows は、窓が受け取れない間の自動の繰り返しを1つの知らせにまとめ、回数だけ添える。
        # Tk は回数を見ないので、遅れている間に押し続けた分の改行が入らずに消えていた・2026-11-07 実測 61回で41行）
        count = max(0, own - 1)
        stats and stats.__setitem__('own_max', max(stats.get('own_max', 0), own))
        while count < MAX_BATCH:
            got = _queued_return(user, MSG, ctypes)
            if not got:
                break
            count += got
        if not count:
            return None
        separators = bool(int(widget.cget('autoseparators')))
        for _ in range(count):
            # Tk の Text の <Return> と同じ（改行1つ・元に戻すの区切り1つ）
            widget.tk.call('tk::TextInsert', widget._w, '\n')
            if separators:
                widget.edit_separator()
        if stats is not None:
            stats['presses'] += count
            stats['batched'] += count
            stats['batches'] += 1
            stats['largest'] = max(stats['largest'], count + 1)
    except Exception as error:
        if stats is not None:
            stats['error'] = repr(error)[:200]
        return None
    return None
