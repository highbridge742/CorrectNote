# -*- coding: utf-8 -*-
"""同じ読みの選び違い（名詞＋を＋動詞・名詞＋の＋形容詞・片仮名＋化＋片仮名）（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import correction_entry as CE
import gen_adj_noun as G
import kata_ka_parallel as K
import semantic_fit as F


class SameReadingVerb(unittest.TestCase):
    def test_other_reading_alternatives(self):
        # 描く は解析で えがく と読むが、かく と打って選び違えた所なので 書く も候補に入る
        self.assertIn((3, 5, '書く'), F.propose('手紙を描く'))

    def test_switch_readings(self):
        os.environ['CN_SF_VERB_ALL_READINGS'] = '0'
        try:
            self.assertNotIn((3, 5, '書く'), F.propose('手紙を描く'))
        finally:
            del os.environ['CN_SF_VERB_ALL_READINGS']

    def test_swap_guard_same_reading(self):
        res = {'original': '手紙を描く', 'corrected': '手紙を書く', 'changed': True, 'details': [], 'odd_spans': []}
        self.assertEqual(CE._kanji_swap_guard('手紙を描く', res)['corrected'], '手紙を書く')

    def test_swap_guard_other_reading_kept(self):
        # 読みが1字違うだけ（いく／あく）の別の動詞へは広げない
        res = {'original': '駅に行く', 'corrected': '駅に開く', 'changed': True, 'details': [], 'odd_spans': []}
        self.assertEqual(CE._kanji_swap_guard('駅に行く', res)['corrected'], '駅に行く')


class GenAdjNoun(unittest.TestCase):
    def test_line_end(self):
        self.assertEqual(G.propose('母の重い。'), [(2, 4, '思い')])

    def test_modifies_noun(self):
        self.assertEqual(G.propose('母の重い荷物'), [])

    def test_switch(self):
        os.environ['CN_GEN_ADJ_NOUN'] = '0'
        try:
            res = {'original': '母の重い。', 'corrected': '母の重い。', 'odd_spans': []}
            self.assertIs(G.repair_line('母の重い。', res), res)
        finally:
            del os.environ['CN_GEN_ADJ_NOUN']


class KataKaParallel(unittest.TestCase):
    def test_mark(self):
        self.assertEqual(K.propose('コピー化ペースト'), [(3, 4)])

    def test_known_word(self):
        self.assertEqual(K.propose('スリム化ボディ'), [])


if __name__ == '__main__':
    unittest.main()
