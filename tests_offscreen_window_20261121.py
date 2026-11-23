# -*- coding: utf-8 -*-
"""試験の窓を、どの画面の置き方でも見えない所に置く（offscreen_window・2026-11-21 うにさんの決まり「試しの窓は画面の外」）。"""
import sys
import time
import tkinter as tk
import unittest

import offscreen_window as O


@unittest.skipUnless(sys.platform == 'win32', 'Windows だけ')
class Hold(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def pump(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def test_outside_every_screen_and_transparent(self):
        O.hold(self.root, '800x500')
        self.pump(0.3)
        self.assertFalse(O.on_a_screen(self.root))
        self.assertEqual(float(self.root.attributes('-alpha')), 0.0)
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), (800, 500))
        self.assertTrue(self.root.winfo_ismapped())                      # 出ている（試験は普通に描ける）

    def test_put_back_when_moved_onto_a_screen(self):
        O.hold(self.root, '600x400')
        self.root.geometry('600x400+100+100')                            # アプリや試験が画面の中へ動かした
        self.pump(0.8)
        self.assertFalse(O.on_a_screen(self.root))


if __name__ == '__main__':
    unittest.main()
