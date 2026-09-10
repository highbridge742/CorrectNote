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
                            ('N', 'じゃわます'), ('TSU', 'ちゃわます'),
                            ('N', 'じゃ'), ('TSU', 'ちゃ')):
            with self.subTest(state=state, tail=tail):
                self.assertFalse(explain_kana_run(tail, initial_state=state))


if __name__ == '__main__':
    unittest.main()
