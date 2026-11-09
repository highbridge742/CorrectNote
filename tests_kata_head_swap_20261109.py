# -*- coding: utf-8 -*-
"""漢字の語の読みの最後の字と助詞が入れ替わり、片仮名の語の頭が欠けた打ち違い（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import kata_head_swap as K


class KataHeadSwap(unittest.TestCase):
    def test_swap(self):
        # まえでだうんろーど を まえだでうんろーど と打った形
        self.assertEqual(K.propose('前田でウンロード'), [(0, 8, '前でダウンロード')])

    def test_general_head_kept(self):
        self.assertEqual(K.propose('山田でブルースを聞く'), [])

    def test_correct_line(self):
        self.assertEqual(K.propose('前でダウンロード'), [])

    def test_switch(self):
        os.environ['CN_KATA_HEAD_SWAP'] = '0'
        try:
            res = {'original': '前田でウンロード', 'corrected': '前田でウンロード', 'odd_spans': []}
            self.assertIs(K.repair_line('前田でウンロード', res), res)
        finally:
            del os.environ['CN_KATA_HEAD_SWAP']


if __name__ == '__main__':
    unittest.main()
