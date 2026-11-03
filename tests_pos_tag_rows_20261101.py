# -*- coding: utf-8 -*-
"""品詞の大きさを塗るとき、どの行に品詞のタグが既に在るかを、窓ごとに1回ずつ聞く（boundary_colors._bare_rows・
2026-11-01・スクロールの重さ）。前は塗った行のたびに、品詞のタグ全部を文末まで探していた（3,600行のタブを
60回送って 15秒のうち 6秒）。答え（その行を消してから塗るか）は同じ。"""
import tkinter as tk
import unittest
from types import SimpleNamespace

import boundary_colors


class BareRowsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.text = tk.Text(self.root)
        self.text.insert('1.0', '\n'.join('行%dの文です' % i for i in range(1, 201)))
        self.colors = boundary_colors.BoundaryColors.__new__(boundary_colors.BoundaryColors)
        self.colors.widget = self.text
        self.colors._row_tags = lambda: (('pos_a', '名詞'), ('pos_b', '助詞'), ('pos_c', '動詞'))

    def tearDown(self):
        self.root.destroy()

    def bare_rows(self, rows, span=64):
        bare = self.colors._bare_rows(span)
        return [row for row in rows if not bare(row)]

    def test_tagged_rows_are_found_across_windows(self):
        for row, tag in ((3, 'pos_a'), (3, 'pos_b'), (70, 'pos_b'), (130, 'pos_c'), (131, 'pos_a')):
            self.text.tag_add(tag, f'{row}.1', f'{row}.3')
        self.assertEqual(self.bare_rows(range(1, 201)), [3, 70, 130, 131])
        self.assertEqual(self.bare_rows(range(1, 201), span=5), [3, 70, 130, 131])
        self.assertEqual(self.bare_rows([2, 70, 71, 199]), [70])       # 飛び飛びの行でも

    def test_an_untagged_text_asks_each_tag_once(self):
        calls = []
        real = self.text.tag_nextrange
        self.text.tag_nextrange = lambda *a: calls.append(a) or real(*a)
        self.assertEqual(self.bare_rows(range(1, 201)), [])
        self.assertEqual(len(calls), 3)

    def test_paint_row_asks_only_for_a_row_it_paints(self):
        asked = []
        colors = self.colors
        colors._painted = {1: ('行1の文です', ('plan',))}
        colors._marker_indices = {}
        colors.app = SimpleNamespace()
        boundary_colors_plan = boundary_colors.plan_for
        try:
            boundary_colors.plan_for = lambda app, w, row, text: None
            colors._has_pos_tags = lambda row: False
            colors.queue_draw = lambda: None
            colors.paint_row(1, bare=lambda row: asked.append(row) or True)
            colors.paint_row(2, bare=lambda row: asked.append(row) or True)
        finally:
            boundary_colors.plan_for = boundary_colors_plan
        self.assertEqual(asked, [2])


if __name__ == '__main__':
    unittest.main()
