# -*- coding: utf-8 -*-
"""変換ミスの残り（同じ読みの動詞の入れ替えを分類で支える・位置の語＋に・読点で終わる連用形）（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import correction_entry as CE
import semantic_fit as F
from morphology import tokenize


class VerbSwapSupported(unittest.TestCase):
    def test_supported(self):
        self.assertTrue(F.verb_swap_supported('を', 'ノート', '描く', '書く'))

    def test_not_supported(self):
        self.assertFalse(F.verb_swap_supported('を', '風景', '描く', '書く'))

    def test_switch(self):
        os.environ['CN_SF_SWAP_SUPPORT'] = '0'
        try:
            self.assertFalse(F.verb_swap_supported('を', 'ノート', '描く', '書く'))
        finally:
            del os.environ['CN_SF_SWAP_SUPPORT']


class PlaceNi(unittest.TestCase):
    def test_place(self):
        t = list(tokenize('机の上に置く'))
        self.assertTrue(CE._frame_place_ni(t[2], t[3]))
        self.assertFalse(CE._frame_place_ni(t[0], t[1]))


class RenyouComma(unittest.TestCase):
    def _res(self, line, fixed):
        return {'original': line, 'corrected': fixed, 'changed': True, 'details': [], 'odd_spans': []}

    def test_comma_keeps(self):
        out = CE._fix_breaks_grammar('箱に本を摘め、', self._res('箱に本を摘め、', '箱に本を詰め、'))
        self.assertEqual(out['corrected'], '箱に本を詰め、')

    def test_switch(self):
        os.environ['CN_FIX_RENYOU_COMMA'] = '0'
        try:
            out = CE._fix_breaks_grammar('箱に本を摘め、', self._res('箱に本を摘め、', '箱に本を詰め、'))
            self.assertEqual(out['corrected'], '箱に本を摘め、')
        finally:
            del os.environ['CN_FIX_RENYOU_COMMA']


if __name__ == '__main__':
    unittest.main()
