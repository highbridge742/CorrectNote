# -*- coding: utf-8 -*-
"""本文の欄そのもののタッチ（2026-11-16 うにさん「1本指ドラッグでスクロールにならず、範囲選択になりました」）。
字の上・絵のないテーマでは、タッチが本文の欄（Text の窓）に直に届き、マウスのドラッグとして選択になっていた。
決まり（touch_step）と、自分の Tk の窓へ送った知らせ（タッチの印は差し替え）で確かめる。ほかの窓へは送らない。"""
import sys
import tkinter as tk
import unittest
from unittest import mock

import paper_window as P

TOUCH, MOUSE = True, False


class Rules(unittest.TestCase):
    def test_touch_move_scrolls_and_does_not_select(self):
        state = {}
        self.assertEqual(P.touch_step(state, P.WM_LBUTTONDOWN, 300, TOUCH), (0, True))      # タップはカーソルを置く
        sent = []
        for y in range(290, 150, -10):
            delta, keep = P.touch_step(state, P.WM_MOUSEMOVE, y, TOUCH)
            self.assertFalse(keep)                                                       # 選択を広げない
            sent.append(delta)
        self.assertLess(sum(sent), 0)                                                   # 指を上へ＝下へ送る
        self.assertTrue(all(d % P.WHEEL_DELTA == 0 for d in sent))
        self.assertEqual(P.touch_step(state, P.WM_LBUTTONUP, 150, TOUCH), (0, True))

    def test_pan_gesture_owns_the_scroll(self):
        state = {}
        P.touch_step(state, P.WM_LBUTTONDOWN, 300, TOUCH)
        self.assertEqual(P.touch_step(state, P.WM_GESTURE, 0, TOUCH, gesture_y=300), (0, False))
        delta, keep = P.touch_step(state, P.WM_GESTURE, 0, TOUCH, gesture_y=300 - 3 * P.PAN_WHEEL_PX)
        self.assertEqual((delta, keep), (-3 * P.WHEEL_DELTA, False))
        self.assertEqual(P.touch_step(state, P.WM_MOUSEMOVE, 200, TOUCH), (0, False))    # 二重に送らない

    def test_mouse_is_untouched(self):
        state = {}
        for msg in (P.WM_LBUTTONDOWN, P.WM_MOUSEMOVE, P.WM_LBUTTONUP):
            self.assertEqual(P.touch_step(state, msg, 100, MOUSE), (0, True))

    def test_signature(self):
        self.assertTrue(P.from_touch(0xFF515780))          # タッチ（0x80）
        self.assertTrue(P.from_touch(0xFF515700))          # ペン
        self.assertFalse(P.from_touch(0))
        self.assertFalse(P.text_touch_enabled({'CN_TEXT_TOUCH': '0'}))
        self.assertTrue(P.text_touch_enabled({}))


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class OnTheWindow(unittest.TestCase):
    """自分の Text の窓に手続きを掛け、その窓へだけ知らせを送る。本物のタッチの代わりに、タッチの印
    （GetMessageExtraInfo）を差し替える。手続きの下に記録の手続きを置き、通った知らせを見る（Tk の扱いは見ない:
    送った知らせは、本物のボタンの状態が無いので Tk のドラッグにならない）。"""
    def setUp(self):
        import ctypes
        import ctypes.wintypes as wt
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.geometry('400x300+40+40')
        self.addCleanup(self.root.destroy)
        self.text = tk.Text(self.root)
        self.text.pack(fill='both', expand=True)
        self.root.update()
        self.hwnd = int(self.text.winfo_id())
        _c, self.user32, comctl = P._load()
        self.got = []
        PROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                  ctypes.c_size_t, ctypes.c_size_t)

        def record(hwnd, msg, wparam, lparam, uid, data):
            if msg == P.WM_MOUSEWHEEL:
                self.got.append(('wheel', ctypes.c_short((wparam >> 16) & 0xFFFF).value, lparam))
                return 0
            if msg in (P.WM_MOUSEMOVE, P.WM_LBUTTONDOWN, P.WM_LBUTTONUP):
                # 試験が送った知らせ（x=50 の所・wParam に印 0x4E00）だけ数える。指が窓の上にあると、窓が出た時に本物の
                # WM_MOUSEMOVE が1つ来て数がずれた（2026-11-20・試験の側の直し）
                if (wparam & 0xFF00) == 0x4E00 and ctypes.c_short(lparam & 0xFFFF).value == 50:
                    self.got.append((msg, None))
                return 0
            return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)
        self.recorder = PROC(record)
        self.assertTrue(comctl.SetWindowSubclass(self.hwnd, self.recorder, 0x5446, 0))      # 下（先に掛けた方が後に走る）
        self.addCleanup(lambda: comctl.RemoveWindowSubclass(self.hwnd, self.recorder, 0x5446))
        self.assertTrue(P.attach_text_touch(self.hwnd))                                  # 上
        self.addCleanup(lambda: P.detach_text_touch(self.hwnd))

    def post(self, msg, x, y, buttons=0):
        self.user32.PostMessageW(self.hwnd, msg, buttons | 0x4E00, ((y & 0xFFFF) << 16) | (x & 0xFFFF))
        for _ in range(3):
            self.root.update()

    def drag(self, touch):
        extra = 0xFF515780 if touch else 0
        with mock.patch.object(self.user32, 'GetMessageExtraInfo', lambda: extra):
            self.post(P.WM_LBUTTONDOWN, 50, 250, 1)
            for y in range(240, 60, -20):
                self.post(P.WM_MOUSEMOVE, 50, y, 1)
            self.post(P.WM_LBUTTONUP, 50, 60, 0)
        for _ in range(5):
            self.root.update()

    def test_touch_drag_scrolls_and_does_not_reach_the_selection(self):
        self.drag(True)
        moves = [g for g in self.got if g[0] == P.WM_MOUSEMOVE]
        wheels = [g[1] for g in self.got if g[0] == 'wheel']
        self.assertEqual(moves, [])                                     # 動きは Text へ渡さない（選択にならない）
        self.assertTrue(wheels and sum(wheels) < 0, self.got)            # 指を上へ＝下へ送るホイール
        self.assertIn((P.WM_LBUTTONDOWN, None), self.got)               # タップ（押し・離し）は通す
        self.assertIn((P.WM_LBUTTONUP, None), self.got)

    def test_mouse_drag_is_untouched(self):
        self.drag(False)
        self.assertEqual(len([g for g in self.got if g[0] == P.WM_MOUSEMOVE]), 9)
        self.assertEqual([g for g in self.got if g[0] == 'wheel'], [])

    # 2026-11-20 うにさん「タッチモニター1本指でスクロールにならない」: 11-18 の長押しの語選び・範囲の掴み（drag_move）は
    # 指の押しも受けていた。指の動きはここで Tk へ渡さないので、drag_move は動いたことを知らず、なぞりの途中で長押しが
    # 立って語を選び、選んだ範囲の中に指を置くと掴み（'armed'・押しの束縛を 'break'）になっていた
    def touch_press(self, touch=True):
        extra = 0xFF515780 if touch else 0
        with mock.patch.object(self.user32, 'GetMessageExtraInfo', lambda: extra):
            self.post(P.WM_LBUTTONDOWN, 50, 250, 1)

    def drag_setup(self):
        import drag_move
        from types import SimpleNamespace as NS
        self.text.configure(font=('Courier New', 12))
        self.text.insert('1.0', 'alpha beta gamma delta')
        self.root.update()
        d = drag_move.install(NS(_show_copy_frame=lambda *a: None, _clear_copy_emphasis=lambda: None,
                                 _on_change=lambda *a: None, _title_toc=None, _word_drag=None), self.text)
        self.text.tag_add('sel', '1.6', '1.10')                                       # 'beta'
        x, y, w, h = self.text.bbox('1.7')
        return drag_move, d, NS(x=x + w // 2, y=y + h // 2, state=0)

    def pump(self, sec):
        import time
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def test_finger_press_does_not_grab_or_long_press(self):
        drag_move, d, inside = self.drag_setup()
        self.touch_press(True)
        self.assertTrue(P.press_is_touch(self.text))
        self.assertIsNone(d.press(inside))                                           # 範囲の中でも掴まない
        self.assertIsNone(d.state)
        self.assertIsNone(d.timer)                                                    # 長押しの時計を立てない
        from types import SimpleNamespace as NS
        x, y, w, h = self.text.bbox('1.18')                                           # 'delta' の上
        self.text.tag_remove('sel', '1.0', 'end')
        d.press(NS(x=x + 2, y=y + h // 2, state=0))
        self.assertIsNone(d.timer)
        self.pump(drag_move.LONGPRESS_MS / 1000.0 + 0.2)
        self.assertFalse(self.text.tag_ranges('sel'))                                # 語を選ばない
        d.release(NS(x=x + 2, y=y + h // 2, state=0))

    def test_mouse_press_still_grabs_and_old_switch_brings_back_the_cause(self):
        drag_move, d, inside = self.drag_setup()
        self.touch_press(False)
        self.assertFalse(P.press_is_touch(self.text))
        self.assertEqual(d.press(inside), 'break')                                   # マウスは今までどおり掴む
        self.assertEqual(d.state, 'armed')
        d.state = None
        self.touch_press(True)
        with mock.patch.dict('os.environ', {'CN_TOUCH_NO_DRAG': '0'}):
            self.assertEqual(d.press(inside), 'break')                               # 前の形: 指でも掴んでいた（原因）
        d.state = None

    def test_finger_double_tap_selects_the_word_not_the_drag(self):
        import mouse_words
        from types import SimpleNamespace as NS
        _drag_move, d, inside = self.drag_setup()
        self.text.tag_remove('sel', '1.0', 'end')
        self.text.tag_add('sel', '1.0', '1.10')                                       # 'alpha beta'
        self.touch_press(True)
        got = mouse_words._double(NS(_word_drag=None), NS(widget=self.text, x=inside.x, y=inside.y, state=0))
        self.assertEqual(got, 'break')
        self.assertIsNone(d.state)                                                    # 移す側へ渡さない
        self.assertEqual(self.text.get('sel.first', 'sel.last'), 'beta')              # 今までどおり語を選ぶ

    def test_finger_wheel_carries_the_screen_position(self):
        import ctypes
        import ctypes.wintypes as wt
        self.drag(True)
        pt = wt.POINT(50, 0)
        self.user32.ClientToScreen(wt.HWND(self.hwnd), ctypes.byref(pt))
        # 指から作ったホイールは、なぞった所（欄の x=50）の画面の位置を持つ。本物のホイール（指が窓の上にある時に
        # 回したもの）が混ざることがあるので、x で見分ける
        xs = [ctypes.c_short(g[2] & 0xFFFF).value for g in self.got if g[0] == 'wheel']
        self.assertIn(pt.x, xs)                                                       # 画面の位置
        self.assertNotIn(50, xs)                                                      # 欄の中の位置のままではない
        with mock.patch.dict('os.environ', {'CN_TOUCH_WHEEL_SCREEN': '0'}):
            self.assertEqual(P.wheel_screen_xy(self.user32, self.hwnd, 50, 60), (50, 60))   # 前の形

    def test_switch_off_attaches_nothing(self):
        with mock.patch.dict('os.environ', {'CN_TEXT_TOUCH': '0'}):
            self.assertFalse(P.attach_text_touch(self.hwnd + 0))


if __name__ == '__main__':
    unittest.main()
