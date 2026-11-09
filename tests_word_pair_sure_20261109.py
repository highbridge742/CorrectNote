# -*- coding: utf-8 -*-
"""語の組の段: 候補1つで行の並びがはっきり自然になる所は紫を付けずに置く（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import word_pair_mark as W


class WordPairSure(unittest.TestCase):
    def test_sure(self):
        # 会議｜室 を IME が 懐疑｜室 にした形（読みをつなぐと身近な1語）
        self.assertTrue(W._sure('懐疑室に集まる', 0, 3, '会議室'))

    def test_not_sure(self):
        self.assertFalse(W._sure('会議室に集まる', 0, 3, '懐疑室'))

    def test_switch(self):
        os.environ['CN_WORD_PAIR_SURE'] = '0'
        try:
            self.assertFalse(W._sure('懐疑室に集まる', 0, 3, '会議室'))
        finally:
            del os.environ['CN_WORD_PAIR_SURE']


if __name__ == '__main__':
    unittest.main()
