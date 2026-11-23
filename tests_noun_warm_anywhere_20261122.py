# -*- coding: utf-8 -*-
"""周りの名詞の下ごしらえは、カーソルがどこで止まっても始める（2026-11-22・軽量化）。前は行頭で止まった時だけで、行末から
空の行へ移ってすぐ F5 を押すと、周りの約70行の名詞を本体でその場で数えて一覧が開くまで約 240ms 待った。数える関数・
並べ方は同じなので、出る名詞は変わらない。CN_AUTO_NOUN_WARM_ANYWHERE=0 で前の形。Tk の窓は出さない（作った字だけ）。"""
import os
import time
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC
import f5_predict as F


class Warm(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        self.w.insert('1.0', '\n'.join('%d行目は会議の資料を確認する作った文です。' % i for i in range(1, 30)))
        self.app = NS(root=self.root, editor=self.w)
        F._NOUN_MEMO.clear()
        self.addCleanup(F._NOUN_MEMO.clear)

    def run_warm(self):
        AC.warm_nouns(self.app, self.w)
        end = time.monotonic() + 5
        while time.monotonic() < end and getattr(self.app, '_noun_warm_job', None) is not None:
            self.root.update()
            time.sleep(0.005)

    def test_line_end_warms_too(self):
        self.w.mark_set('insert', '10.end')                     # 行末（前は下ごしらえしなかった）
        self.run_warm()
        line = self.w.get('10.0', '10.end')
        self.assertIn(line, F._NOUN_MEMO)
        self.assertGreater(len(F._NOUN_MEMO), 20)
        # 下ごしらえの後は、F5 の周りの名詞が控えから出る（同じ関数・同じ並び）
        warm = F.around_nouns(self.w, 10)
        F._NOUN_MEMO.clear()
        self.assertEqual(F.around_nouns(self.w, 10), warm)

    def test_switch_back(self):
        self.w.mark_set('insert', '10.end')
        with mock.patch.dict(os.environ, {'CN_AUTO_NOUN_WARM_ANYWHERE': '0'}), \
                mock.patch.object(F, 'after_head', lambda *a: False):
            self.run_warm()
        self.assertEqual(F._NOUN_MEMO, {})                     # 前の形: 行末では始めない


if __name__ == '__main__':
    unittest.main()
