# -*- coding: utf-8 -*-
import unittest
from pos_grammar import explain_kana_run


class ColloquialConnectionTests(unittest.TestCase):
    def test_unvoiced_onbin_contraction(self):
        for tail in ('ちゃう', 'ちゃった', 'ちゃわない', 'ちゃいます',
                     'ちゃえば', 'ちゃおう', 'ちゃって', 'ちゃわなかった'):
            with self.subTest(tail=tail):
                self.assertTrue(explain_kana_run(tail, initial_state='TSU'))

    def test_voiced_onbin_contraction(self):
        for tail in ('じゃう', 'じゃった', 'じゃわない', 'じゃいます',
                     'じゃえば', 'じゃおう', 'じゃって', 'じゃわなかった'):
            with self.subTest(tail=tail):
                self.assertTrue(explain_kana_run(tail, initial_state='N'))

    def test_ichidan_contraction(self):
        for tail in ('ちゃわない', 'ちゃえば', 'ちゃおう'):
            self.assertTrue(explain_kana_run(tail, initial_state='E'))

    def test_wrong_voice_and_incomplete_conjugation(self):
        for state, tail in (('N', 'ちゃう'), ('TSU', 'じゃう'),
                            ('N', 'じゃわます'), ('TSU', 'ちゃわます')):
            with self.subTest(state=state, tail=tail):
                self.assertFalse(explain_kana_run(tail, initial_state=state))

    def test_contracted_tewa_before_next_clause(self):
        # ては・では の縮まった ちゃ・じゃ は、後ろの文節（駄目・いけない）の前で切れる（見ちゃ駄目・遊んじゃいけない）。
        # 2026-11-06 batch157 から。終助詞・助動詞は直に付かない（上の ちゃわます）
        for state, tail in (('N', 'じゃ'), ('TSU', 'ちゃ'), ('TSU', 'ちゃだめ'), ('N', 'じゃいけない')):
            with self.subTest(state=state, tail=tail):
                self.assertTrue(explain_kana_run(tail, initial_state=state))


if __name__ == '__main__':
    unittest.main()
