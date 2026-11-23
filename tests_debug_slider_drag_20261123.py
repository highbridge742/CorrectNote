# -*- coding: utf-8 -*-
"""デバッグメニューのスライダーを、溝を押してすぐ左右に引いて動かせる（2026-11-23 うにさん「デバッグのスライダーが動かし
づらくなった。クリックしてすぐ左右にドラッグしても動かない」）。Tk の Windows の作りでは、つまみの外（溝）を押すと1目盛り
動くだけで、そのまま引いても動かなかった（つまみの上を押した時だけ引ける）。押した所へつまみを動かし、そのまま引ける形に。
あわせて下の「すべてデフォルトに戻す」「閉じる」を出さない（同じ日のうにさんの指定・窓の×で閉じる。各項目の
「デフォルトに戻す」は残す）。CN_DEBUG_SLIDER_DRAG=0・CN_DEBUG_NO_RESET_CLOSE=0 で前の形。画面の外に置く。"""
import os
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

import app
import debug_menu
from settings import Settings


class SliderDrag(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = tk.Tk(); __import__('offscreen_window').hold(self.root, '200x100')
        self.addCleanup(self.root.destroy)
        self.a = object.__new__(app.CorrectNoteApp)
        self.a.settings = Settings(os.path.join(self.dir.name, 'settings.json'))
        self.a.root = self.root
        self.a._place_dialog = lambda dlg, w, h: __import__('offscreen_window').hold(dlg, '%dx%d' % (w, h))
        self.addCleanup(debug_menu.apply, object.__new__(app.CorrectNoteApp), {})
        self.t = int(time.monotonic() * 1000)

    def settle(self):
        for _ in range(15):
            self.root.update(); time.sleep(0.01)

    def open(self):
        dlg = self.a.open_debug_menu()
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        self.settle()
        return dlg

    def drag(self, scale, x0, x1):
        y = scale.winfo_height() // 2
        self.t += 1000
        scale.event_generate('<ButtonPress-1>', x=x0, y=y, time=self.t)
        self.settle()
        after_press = scale.get()
        for k in range(1, 6):
            x = x0 + (x1 - x0) * k // 5
            scale.event_generate('<B1-Motion>', x=x, y=y, state=0x100, time=self.t + 20 * k)
            self.settle()
        moved = scale.get()
        scale.event_generate('<ButtonRelease-1>', x=x1, y=y, state=0x100, time=self.t + 200)
        self.settle()
        return after_press, moved

    def test_press_on_the_trough_then_drag(self):
        dlg = self.open()
        row = dlg._debug_rows['copy_emphasis']
        scale = row['scale']
        width = scale.winfo_width()
        self.assertGreater(width, 100)
        want = int(float(scale.tk.call(scale._w, 'get', width - 20, scale.winfo_height() // 2)))
        press, moved = self.drag(scale, 12, width - 20)              # 左の端の溝を押して、すぐ右へ引く
        self.assertLessEqual(abs(moved - want), 2, (press, moved, want))   # 引いた所の値になる（つまみを掴んだ位置のずれで±1）
        self.assertLess(press, 110, (press, moved))                  # 押した所（左の端）へつまみが動いた
        self.assertEqual(row['number'].get(), moved)
        self.assertEqual(debug_menu.values(self.a)['copy_emphasis'], moved)   # 当てた

    def test_switch_back_drag(self):
        with mock.patch.dict(os.environ, {'CN_DEBUG_SLIDER_DRAG': '0'}):
            dlg = self.open()
        scale = dlg._debug_rows['copy_emphasis']['scale']
        width = scale.winfo_width()
        before = scale.get()
        want = int(float(scale.tk.call(scale._w, 'get', width - 20, scale.winfo_height() // 2)))
        press, moved = self.drag(scale, 12, width - 20)
        # 前の形: 溝を押すと押した側へ1目盛りずつ進むだけで、右へ引いても右へは動かない
        self.assertLessEqual(moved, before, (before, press, moved, want))
        self.assertGreater(want - moved, 20, (before, press, moved, want))

    def buttons(self, dlg):
        got = []
        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() == 'Button':
                    got.append(str(c.cget('text')))
                walk(c)
        walk(dlg)
        return got

    def test_no_reset_all_and_close_buttons(self):
        dlg = self.open()
        names = self.buttons(dlg)
        self.assertNotIn('すべてデフォルトに戻す', names)
        self.assertNotIn('閉じる', names)
        self.assertIn('デフォルトに戻す', names)                       # 各項目のは残す
        self.assertTrue(callable(dlg._debug_reset_all))

    def test_switch_back_buttons(self):
        with mock.patch.dict(os.environ, {'CN_DEBUG_NO_RESET_CLOSE': '0'}):
            dlg = self.open()
        names = self.buttons(dlg)
        self.assertIn('すべてデフォルトに戻す', names)
        self.assertIn('閉じる', names)


if __name__ == '__main__':
    unittest.main()
