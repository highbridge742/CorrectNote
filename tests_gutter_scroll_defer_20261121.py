# -*- coding: utf-8 -*-
"""スクロールの間は行番号を描き直さず、止まってから1回（2026-11-21 軽量化・うにさんの選んだ「試す」(B)）。
既定はオフ（うに 11-21 14:14Z「ホイールでスクロールすると行番号が付いてこない」）: スクロールの間もその場で描く
（前の形）。CN_GUTTER_SCROLL_DEFER=1 で止まってから描く形。自分の Tk の窓だけ（画面の外）・作った例文。"""
import os
import time
import tkinter as tk
import unittest
from unittest import mock

import app as A


class GutterDefer(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        import offscreen_window; offscreen_window.hold(self.root, '400x300')
        self.text = tk.Text(self.root)
        self.text.insert('1.0', '\n'.join('%d行目' % i for i in range(1, 200)))
        self.g = A.LineNumberGutter(self.root, self.text)
        self.g.pack(side='left', fill='y')
        self.text.pack(side='left', fill='both', expand=True)
        self.root.update()
        self.drawn = []
        real = A.LineNumberGutter.redraw

        def counting(this):
            if not this._defer_while_scrolling():
                self.drawn.append(time.monotonic())
            return real(this)
        p = mock.patch.object(A.LineNumberGutter, 'redraw', counting)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.root.destroy)
        A.LineNumberGutter.scrolling_until = 0.0

    def pump(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def test_default_draws_while_scrolling(self):
        # 既定（うに 11-21 14:14Z 行番号が付いてこない）: スクロールの間も本文と一緒にその場で描く
        A.LineNumberGutter.scrolling_until = time.monotonic() + 0.08
        for _ in range(5):
            self.g.redraw()
        self.assertEqual(len(self.drawn), 5)

    def test_defer_switch(self):
        with mock.patch.dict(os.environ, {'CN_GUTTER_SCROLL_DEFER': '1'}):
            A.LineNumberGutter.scrolling_until = time.monotonic() + 0.08
            for _ in range(5):
                self.g.redraw()
            self.assertEqual(self.drawn, [])                               # スクロールの間は描かない
            self.pump(0.2)
            self.assertEqual(len(self.drawn), 1)                           # 止まってから1回

    def test_not_scrolling_draws_at_once(self):
        self.g.redraw()
        self.assertEqual(len(self.drawn), 1)


if __name__ == '__main__':
    unittest.main()
