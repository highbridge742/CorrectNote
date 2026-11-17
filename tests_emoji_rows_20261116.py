# -*- coding: utf-8 -*-
"""色付きの絵文字の置き場所と、本文の中のタイトル・目次（2026-11-16 うにさん: 目次が2行ある時、1行目の「甲😀」が
白黒で、空の5行目に絵文字が出た）。見出しの行の中の点（@0,0）から読み始めると、読んだ字には見出しの行が入るのに、
行の番号は本文の1行目になり、絵文字が見出しの行数ぶん下へずれていた。自分の Tk の窓だけ・作った例文。"""
import os
import sys
import tkinter as tk
import unittest
from unittest import mock

import emoji_color as E
import title_inline as TI

TEXT = '甲\U0001F600\n2行目\n3行目\n4行目\n\n6行目'


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class EmojiUnderTheHeader(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.geometry('500x400+40+40')
        self.addCleanup(self.root.destroy)

    def pane(self, header):
        t = tk.Text(self.root, font=('Meiryo', 11))
        if header:
            TI.prepare(t)
            TI.style(t, 'Meiryo', 12, '#1f5fbf', '#888888')
            TI.write(t, '試しの題', [(2, 2, '2行目'), (4, 4, '4行目')])         # 目次2行
        t.pack(fill='both', expand=True)
        t.insert('1.0', TEXT)
        overlay = E.install(t)
        if overlay is None:
            self.skipTest('no colour emoji here')
        self.root.update()
        return t, overlay

    def check(self, t, overlay):
        placed = overlay.placements()
        self.assertEqual([p[4] for p in placed], ['\U0001F600'])
        x, y, w, h = placed[0][:4]
        row1 = t.dlineinfo('1.0')                 # 本文の1行目（見出しの下）
        self.assertTrue(row1[1] <= y < row1[1] + row1[3], (placed, row1))
        row5 = t.dlineinfo('5.0')
        self.assertFalse(row5[1] <= y < row5[1] + row5[3])

    def test_without_header(self):
        self.check(*self.pane(False))

    def test_with_title_and_two_toc_rows(self):
        t, overlay = self.pane(True)
        t.yview_moveto(0)
        self.root.update()
        self.assertTrue(int(str(t.tk.call(t._cn_body_raw, 'index', '@0,0')).split('.')[0]) <= TI.head_rows(t))
        self.check(t, overlay)

    def test_switch_back(self):
        t, overlay = self.pane(True)
        t.yview_moveto(0)
        self.root.update()
        with mock.patch.dict(os.environ, {'CN_EMOJI_HEAD_ROWS': '0'}):
            placed = overlay.placements()
        # 前の動き: 見出しの行数（タイトル1・目次2・線1＝4）ぶん下の、空の5行目に置いた（うにさんの見た形）
        self.assertTrue(placed)
        row5 = t.dlineinfo('5.0')
        self.assertTrue(row5[1] <= placed[0][1] < row5[1] + row5[3], (placed, row5))


if __name__ == '__main__':
    unittest.main()
