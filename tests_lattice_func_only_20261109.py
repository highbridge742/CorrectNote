# -*- coding: utf-8 -*-
"""batch424: 掛かる語が 形式名詞・接尾・助詞・助動詞 だけの所は、格子の表記の迷いの紫にしない（kana_lattice_place）。"""
import unittest

import kana_lattice_place as K


class LatticeFuncOnly(unittest.TestCase):
    def test_name_suffix(self):
        t = 'ブラウンさんの家です。'
        self.assertFalse([d for d in K.propose(t, None, None)[1] if t[d[0]:d[1]] == 'さん'])


if __name__ == '__main__':
    unittest.main()
