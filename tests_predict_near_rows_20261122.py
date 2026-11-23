# -*- coding: utf-8 -*-
"""予測で本文を読むのはカーソルの行の上下40行まで（2026-11-22 03:13Z うにさん「予測変換の名詞の数は、上下何行の範囲から
取っている？もし全体を見ているなら範囲を絞る」）。名詞（around_nouns）は前から上下40行。前の文と「タブに全角の字があるか」
はタブ全体を読んでいた。CN_PREDICT_NEAR_ROWS=0 で前の形。作った字だけ。run_on_desktop で回す。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import f5_predict as F


class NearRows(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        # 1行目だけ全角。2〜199行目は半角で句点なし（前の文がずっと続く形）
        self.w.insert('1.0', '全角の行。\n' + '\n'.join('row %d' % r for r in range(2, 200)))
        self.w.mark_set('insert', '150.end')

    def test_reads_only_near_rows(self):
        self.assertEqual(F._near_start(self.w), '110.0')
        self.assertEqual(F._near_start(self.w, 20), '1.0')
        self.assertEqual(F._near_end(self.w, 150), '190.end')
        sentence = F.previous_sentence(self.w, 'row 150')
        self.assertTrue(sentence.startswith('row 110'), sentence)     # 40行より上は読まない
        whole = self.w.get(F._near_start(self.w, 150), F._near_end(self.w, 150))
        self.assertFalse(F.has_wide(whole))                           # 1行目の全角は範囲の外

    def test_nouns_were_already_near(self):
        self.assertEqual(F.AROUND_ROWS, 40)

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_NEAR_ROWS': '0'}):
            self.assertEqual(F._near_start(self.w), '1.0')
            self.assertEqual(F._near_end(self.w, 150), 'end-1c')
            self.assertTrue(F.previous_sentence(self.w, 'row 150').startswith('row 2'))


if __name__ == '__main__':
    unittest.main()
