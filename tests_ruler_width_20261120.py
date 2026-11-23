# -*- coding: utf-8 -*-
"""ルーラー・最終行の下の二重罫線の太さと、補正欄の目次の境目の線（2026-11-20 うにさん）。
「ルーラーが見えにくい。目次と本文の境目の線は見えやすい。太さの違いだけか？今の太さと境目の線の太さの中間にする」
「最終行の下の二重罫線も見えにくい」「目次と本文の境目の線は、補正欄側にも表示する」。
色は3つとも同じ RULE で、違いは太さだけ（ルーラー・二重罫線 1px、境目の線 約3px）。自分の Tk の窓だけ・作った例文。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import editor_guides
import title_inline as TI


class Widths(unittest.TestCase):
    def test_ruler_is_two_pixels_and_switch_back(self):
        self.assertEqual(editor_guides.ruler_width(), 2)
        with mock.patch.dict(os.environ, {'CN_RULER_THIN': '1'}):
            self.assertEqual(editor_guides.ruler_width(), 1)

    def test_end_rule_metrics(self):
        fake = NS(END_RULE_WIDTH=2, END_RULE_GAP=2)
        self.assertEqual(app.CorrectNoteApp._end_rule_metrics(fake), (2, 2))
        with mock.patch.dict(os.environ, {'CN_RULER_THIN': '1'}):
            self.assertEqual(app.CorrectNoteApp._end_rule_metrics(fake), (1, 2))      # 前の形: 1px の線が 3px 置き


class RightPaneRule(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def pane(self):
        t = tk.Text(self.root)
        TI.prepare(t)
        TI.style(t, 'Meiryo', 10, '#1f5fbf', '#abcdef')
        TI.write(t, '題', [(2, 2, '二')], blank=True)                # 補正欄（右）の空の見出し
        return t

    def test_blank_header_draws_the_rule(self):
        t = self.pane()
        self.assertEqual(str(t.tk.call(t._cn_body_raw, 'tag', 'cget', TI.TAG_RULE_BLANK, '-background')), '#abcdef')

    def test_switch_back_leaves_it_blank(self):
        with mock.patch.dict(os.environ, {'CN_TOC_RULE_RIGHT': '0'}):
            t = self.pane()
        self.assertEqual(str(t.tk.call(t._cn_body_raw, 'tag', 'cget', TI.TAG_RULE_BLANK, '-background')), '')


if __name__ == '__main__':
    unittest.main()
