# -*- coding: utf-8 -*-
"""俯瞰（今の形）の間、行番号の列の幅を変えない（2026-11-20 うにさん「左の行のレイアウトが変わることで、本文の行頭位置が
左右に揺れるので、揺れないように」）。小さい字で桁の幅が縮み、本文が左へ寄っていた。自分の Tk の窓だけ。"""
import tkinter as tk
import unittest

import app


class GutterHold(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('400x300+40+40')
        frame = tk.Frame(self.root)
        frame.pack(fill='both', expand=True)
        self.text = tk.Text(frame)
        self.gutter = app.LineNumberGutter(frame, self.text)
        self.gutter.pack(side='left', fill='y')
        self.text.pack(side='left', fill='both', expand=True)
        self.text.insert('1.0', '\n'.join('行%d' % i for i in range(1, 2000)))
        self.root.update()
        self.gutter.redraw()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_held_width_survives_a_smaller_font(self):
        normal = int(self.gutter['width'])
        original = self.gutter.font
        self.gutter.hold_width = normal
        self.gutter.font = ('Meiryo', 5)
        self.gutter.redraw()
        self.assertEqual(int(self.gutter['width']), normal)            # 俯瞰の間も同じ幅
        x_during = self.text.winfo_rootx()
        self.gutter.hold_width = None
        self.gutter.font = original
        self.gutter.redraw()
        self.root.update()
        self.assertEqual(int(self.gutter['width']), normal)
        self.assertEqual(self.text.winfo_rootx(), x_during)            # 本文の欄の左端が動かない

    def test_without_the_hold_the_width_follows_the_font(self):
        normal = int(self.gutter['width'])
        self.gutter.font = ('Meiryo', 5)
        self.gutter.redraw()
        self.assertLess(int(self.gutter['width']), normal)             # 前の動き: 縮んで本文が左へ寄った


if __name__ == '__main__':
    unittest.main()
