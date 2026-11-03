# -*- coding: utf-8 -*-
"""再変換（F5）の範囲を Shift+左右で増減したあとの、Shift なしの左右キー（2026-10-30 うにさん「その時の
選択範囲を境目として、境目を越えたところから選択する」）。右は 2026-08-27 から（_f2_resized_next）、左を足した。"""
import tkinter as tk
import unittest

import app


class F2ResizedLeftTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root)
        line = '今日は資料を確認します'
        self.text.insert('1.0', line)
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        # 今日|は|資料|を|確認|します
        cuts = [(0, 2), (2, 3), (3, 5), (5, 6), (6, 8), (8, 11)]
        self.units = [dict(start=s, end=e, text=line[s:e], reading='') for s, e in cuts]
        self.shown = []
        self.a._show_unit_candidates = lambda row, unit, widget, unified, units: self.shown.append(
            (unit['start'], unit['end']))

    def tearDown(self):
        self.root.destroy()

    def select(self, idx, start, end):
        self.a._f2_cycle = dict(row=1, idx=idx, units=self.units, widget=self.text, unified=False)
        self.a._f2_focus_target = dict(row=1, start=start, end=end, widget=self.text)

    def test_left_after_widening_left_into_a_word_takes_the_rest_of_that_word(self):
        # 「確認」(6,8) を Shift+← で 料を確認 (4,8) へ: 左キーは 資料 の 資 (3,4) から
        self.select(4, 4, 8)
        self.assertEqual(self.a._f2_resized_prev(), 'break')
        self.assertEqual(self.shown, [(3, 4)])
        self.assertEqual(self.a._f2_cycle['idx'], 2)
        self.assertEqual(self.a._f2_peek.__name__, '_f2_peek')

    def test_left_on_a_unit_boundary_joins_the_ordinary_walk(self):
        # 範囲が 資料を確認 (3,8)・始まりは切れ目: 資料 (2) から通常の渡り歩きで左へ（は を飛ばして 今日）
        self.select(4, 3, 8)
        self.assertIsNone(self.a._f2_resized_prev())
        self.assertEqual(self.shown, [])
        self.assertEqual(self.a._f2_cycle['idx'], 2)

    def test_unchanged_range_and_line_start(self):
        self.select(4, 6, 8)                                   # not resized
        self.assertIsNone(self.a._f2_resized_prev())
        self.assertEqual(self.a._f2_cycle['idx'], 4)
        self.select(0, 0, 3)                                   # widened right from the line's head
        self.assertIsNone(self.a._f2_resized_prev())
        self.assertEqual(self.a._f2_cycle['idx'], 0)

    def test_right_still_starts_after_the_range(self):
        self.select(2, 3, 6)                                   # 資料を (3,6) から右は 確認 から通常の道
        self.assertIsNone(self.a._f2_resized_next())
        self.assertEqual(self.a._f2_cycle['idx'], 3)
        self.select(2, 3, 7)                                   # 資料を確 (3,7) から右は 認 (7,8)
        self.assertEqual(self.a._f2_resized_next(), 'break')
        self.assertEqual(self.shown[-1], (7, 8))


if __name__ == '__main__':
    unittest.main()
