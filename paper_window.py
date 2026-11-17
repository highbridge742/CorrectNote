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
# タッチの1本指のなぞり（2026-11-13 うにさん「タッチモニター1本指でスクロールができなくなっている。背景イラストの
# 影響と思われる」）。透かした画素のタッチも OS が後ろの Canvas へ渡すので、なぞり（パンのジェスチャー）は Canvas に
# 届き、本文の欄はスクロールしなかった。タッチの元の知らせ（WM_POINTER*）は PostMessage で送り直せない
# （ERROR_INVALID_MESSAGE）ので、Canvas でパンを受けて、指の動いた縦の量をホイールの知らせにして本文の欄へ送る
# （ホイールの知らせは送り直せて、本文の欄のホイールの束縛がそのまま働く）。CN_PAPER_TOUCH=0 で前の形
WM_GESTURE = 0x0119
WM_MOUSEWHEEL = 0x020A
GID_BEGIN, GID_END, GID_PAN = 1, 2, 4
WHEEL_DELTA = 120
# 指がこの画素だけ動くとホイール1目盛り（120）。本体のホイールは1目盛りで1行（app._on_wheel・ceil(delta/120)）
# なので、だいたい1行の高さにして、指と本文が同じくらい動くようにする
PAN_WHEEL_PX = 24


def pan_wheel(previous_y, y, remainder=0.0, px=PAN_WHEEL_PX):
    """パンの1回ぶんの指の縦の動きを、ホイールの量にする。(送る量, 残り)。指を上へ（y が減る）＝下へ送る＝負の量。
    送るのは1目盛り（120）の倍数だけ（本体は 120 未満の量を、下へは1行・上へは0行に丸めてしまう）。
    目盛りに足りない動きは次へ持ち越す（ゆっくりなぞっても止まらない）。"""
    amount = (y - previous_y) * WHEEL_DELTA / float(px) + remainder
    notches = int(amount / WHEEL_DELTA)
    whole = notches * WHEEL_DELTA
    return whole, amount - whole


def touch_enabled(environ=None):
    import os
    environ = os.environ if environ is None else environ
    return environ.get('CN_PAPER_TOUCH') != '0'

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

        class GESTUREINFO(ctypes.Structure):
            _fields_ = [('cbSize', wt.UINT), ('dwFlags', wt.DWORD), ('dwID', wt.DWORD), ('hwndTarget', wt.HWND),
                        ('x', ctypes.c_short), ('y', ctypes.c_short), ('dwInstanceID', wt.DWORD),
                        ('dwSequenceID', wt.DWORD), ('ullArguments', ctypes.c_ulonglong), ('cbExtraArgs', wt.UINT)]
        try:
            user32.GetGestureInfo.restype = wt.BOOL
            user32.GetGestureInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(GESTUREINFO))
            user32.CloseGestureInfoHandle.restype = wt.BOOL
            user32.CloseGestureInfoHandle.argtypes = (ctypes.c_void_p,)
            gestures = touch_enabled()
        except AttributeError:
            gestures = False
        pans = {}          # Canvas の窓 → [前の指の y, ホイールの端数]

        def pan(hwnd, lparam, target):
            """パンを受けたら True（ホイールを送った・始まり・終わり）。ほかのジェスチャーは False。"""
            info = GESTUREINFO()
            info.cbSize = ctypes.sizeof(GESTUREINFO)
            if not user32.GetGestureInfo(ctypes.c_void_p(lparam), ctypes.byref(info)):
                return False
            if info.dwID == GID_BEGIN:
                pans.pop(hwnd, None)
                return False                     # 始まりは既定の手続きへ（ほかのジェスチャーも決まる）
            if info.dwID == GID_END:
                pans.pop(hwnd, None)
                return False
            if info.dwID != GID_PAN:
                return False
            state = pans.get(hwnd)
            if state is None:
                pans[hwnd] = [info.y, 0.0]
            else:
                delta, state[1] = pan_wheel(state[0], info.y, state[1])
                state[0] = info.y
                if delta:
                    delta = max(-32768, min(32767, delta))
                    user32.PostMessageW(target, WM_MOUSEWHEEL, (delta & 0xFFFF) << 16,
                                        ((info.y & 0xFFFF) << 16) | (info.x & 0xFFFF))
            user32.CloseGestureInfoHandle(ctypes.c_void_p(lparam))
            return True

        def forward(hwnd, msg, wparam, lparam, uid, target):
            # ★ Tk を呼ばない
            if msg in MOUSE_MESSAGES:
                user32.PostMessageW(target, msg, wparam, lparam)
                return 0
            if msg == WM_GESTURE and gestures:
                try:
                    if pan(hwnd, lparam, target):
                        return 0                 # 受けた（閉じた）パンは既定の手続きへ渡さない
                except Exception:
                    pass
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


# --- 本文の欄そのもののタッチ（2026-11-16 うにさん「1本指ドラッグでスクロールにならず、範囲選択になりました」） ----
# 透かした画素のタッチは上の Canvas が受けてホイールにする。透かしていない所（字の上・絵のないテーマ）のタッチは本文の
# 欄（Tk の Text の窓）に直に届き、パンのジェスチャーを誰も受けないので、OS がマウスの押し・動きにして渡し、Tk は
# ドラッグの選択にしていた。本文の欄の窓でも、
#   ・パン（WM_GESTURE・GID_PAN）→ 縦の量をホイールの知らせにして自分へ送る（本文の欄のホイールの束縛がそのまま働く）
#   ・タッチから作られたマウスの動き（GetMessageExtraInfo の MI_WP_SIGNATURE）→ 選択を広げない。パンが来ない時は、その
#     動きをホイールにする
#   ・タッチの押し・離し（タップ）はそのまま通す（カーソルを置く）
# CN_TEXT_TOUCH=0 で前の動き（何も掛けない）。
TOUCH_SUBCLASS_ID = 0x434F       # 'CO'
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
MI_WP_SIGNATURE, SIGNATURE_MASK = 0xFF515700, 0xFFFFFF00
_touch_proc = None
_touch_state = {}               # 本文の欄の窓 → dict(y, rem, gesture, down)


def text_touch_enabled(environ=None):
    import os
    environ = os.environ if environ is None else environ
    return environ.get('CN_TEXT_TOUCH') != '0'


def from_touch(extra):
    """マウスの知らせが、タッチ・ペンから作られた物か（GetMessageExtraInfo の印）。"""
    return (int(extra) & SIGNATURE_MASK) == MI_WP_SIGNATURE


def touch_step(state, msg, y, touch, gesture_y=None):
    """本文の欄の窓が受けた知らせ1つの扱い（決まりだけ・試験から呼べる形）。
    戻り: (送るホイールの量 or 0, この知らせを Tk へ渡すか)。state はこの窓の状態（dict）を書き換える。
      gesture_y: パンのジェスチャーの指の y（パンの知らせの時だけ）。"""
    if gesture_y is not None:
        if not state.get('gesture'):
            state.update(gesture=True, y=gesture_y, rem=0.0)
            return 0, False
        delta, state['rem'] = pan_wheel(state['y'], gesture_y, state.get('rem', 0.0))
        state['y'] = gesture_y
        return delta, False
    if not touch:
        return 0, True
    if msg == WM_LBUTTONDOWN:
        state.clear()
        state.update(down=True, y=y, rem=0.0, gesture=False)
        return 0, True                   # タップはカーソルを置く
    if msg == WM_MOUSEMOVE:
        if not state.get('down'):
            return 0, True
        if state.get('gesture'):
            return 0, False              # パンが送っている。選択を広げない
        delta, state['rem'] = pan_wheel(state.get('y', y), y, state.get('rem', 0.0))
        state['y'] = y
        return delta, False
    if msg == WM_LBUTTONUP:
        state.clear()
        return 0, True
    return 0, True


def _touch_api():
    """本文の欄のタッチの手続き（_load の ctypes を使う）。使えなければ None。"""
    global _touch_proc
    api = _load()
    if api is None:
        return None
    ctypes, user32, comctl = api
    if _touch_proc is not None:
        return api
    import ctypes.wintypes as wt
    LRESULT = ctypes.c_ssize_t
    SUBCLASSPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                      ctypes.c_size_t, ctypes.c_size_t)
    user32.GetMessageExtraInfo.restype = ctypes.c_ssize_t
    user32.GetMessageExtraInfo.argtypes = ()

    class GESTUREINFO(ctypes.Structure):
        _fields_ = [('cbSize', wt.UINT), ('dwFlags', wt.DWORD), ('dwID', wt.DWORD), ('hwndTarget', wt.HWND),
                    ('x', ctypes.c_short), ('y', ctypes.c_short), ('dwInstanceID', wt.DWORD),
                    ('dwSequenceID', wt.DWORD), ('ullArguments', ctypes.c_ulonglong), ('cbExtraArgs', wt.UINT)]

    def post_wheel(hwnd, delta, x, y):
        delta = max(-32768, min(32767, int(delta)))
        user32.PostMessageW(hwnd, WM_MOUSEWHEEL, (delta & 0xFFFF) << 16, ((y & 0xFFFF) << 16) | (x & 0xFFFF))

    def proc(hwnd, msg, wparam, lparam, uid, data):
        # ★ Tk を呼ばない（窓の手続きの中）
        try:
            state = _touch_state.setdefault(int(hwnd), {})
            if msg == WM_GESTURE:
                info = GESTUREINFO()
                info.cbSize = ctypes.sizeof(GESTUREINFO)
                if user32.GetGestureInfo(ctypes.c_void_p(lparam), ctypes.byref(info)):
                    if info.dwID in (GID_BEGIN, GID_END):
                        if info.dwID == GID_END:
                            state.pop('gesture', None)
                    elif info.dwID == GID_PAN:
                        delta, _pass = touch_step(state, msg, 0, True, gesture_y=info.y)
                        if delta:
                            post_wheel(hwnd, delta, info.x, info.y)
                        user32.CloseGestureInfoHandle(ctypes.c_void_p(lparam))
                        return 0
            elif msg in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP):
                touch = from_touch(user32.GetMessageExtraInfo())
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                x = ctypes.c_short(lparam & 0xFFFF).value
                delta, keep = touch_step(state, msg, y, touch)
                if delta:
                    post_wheel(hwnd, delta, x, y)
                if not keep:
                    return 0
            elif msg == WM_NCDESTROY:
                _touch_state.pop(int(hwnd), None)
                comctl.RemoveWindowSubclass(hwnd, _touch_proc, TOUCH_SUBCLASS_ID)
        except Exception:
            pass
        return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)

    _touch_proc = SUBCLASSPROC(proc)
    return api


def attach_text_touch(text_hwnd):
    """本文の欄（Tk の Text の窓）に、タッチのなぞりをスクロールにする手続きを掛ける。掛けたら True。"""
    if not text_touch_enabled() or not text_hwnd:
        return False
    api = _touch_api()
    if api is None:
        return False
    try:
        return bool(api[2].SetWindowSubclass(text_hwnd, _touch_proc, TOUCH_SUBCLASS_ID, 0))
    except Exception:
        return False


def detach_text_touch(text_hwnd):
    api = _touch_api()
    if api is None or not text_hwnd:
        return
    try:
        api[2].RemoveWindowSubclass(text_hwnd, _touch_proc, TOUCH_SUBCLASS_ID)
        _touch_state.pop(int(text_hwnd), None)
    except Exception:
        pass
