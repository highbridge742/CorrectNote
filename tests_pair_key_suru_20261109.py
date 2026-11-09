# -*- coding: utf-8 -*-
"""batch419: 組が 名詞＋する だけの所では1打違いの名詞に直さない（pair_choice）。"""
import os
import unittest

import pair_choice as P


class PairKeySuru(unittest.TestCase):
    def test_suru_only_no_key_fix(self):
        t = '彼は脚本を改作した。'
        self.assertFalse([m for m in P.propose(t) if m[2]])


if __name__ == '__main__':
    unittest.main()
