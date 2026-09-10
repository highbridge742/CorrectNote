# -*- coding: utf-8 -*-
"""最終検査が同じ候補・原文範囲について理由を返すことを確認する。"""
import unittest
from unittest.mock import patch, Mock
import corrector as C


class ReplacementContractTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(C, 'absorb_stray_char', side_effect=lambda line, a, b, value: (a, b)),
            patch.object(C, '_reading_spelled_in_bracket', return_value=False),
            patch.object(C, 'long_vowel_protected_span', return_value=None),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def check(self, original, corrected, **kwargs):
        return C._check_replacement(original, (0, len(original), corrected, 'その他'),
                                    None, None, **kwargs)

    def test_unchanged_is_not_a_replacement(self):
        self.assertEqual(self.check('文章', '文章'), (None, 'unchanged'))

    def test_user_block_is_distinct_from_structural_failure(self):
        decision = Mock()
        decision.blocks.return_value = True
        self.assertEqual(self.check('誤字', '文字', decisions=decision), (None, 'user_block'))
        decision.blocks.assert_called_once_with('誤字', '文字')

    def test_length_and_existing_exemptions(self):
        self.assertEqual(self.check('あいうえお', '字'), (None, 'length_delta'))
        accepted, reason = self.check('あいうえお', '字', lu_taken=[(0, 5)], conv_taken=[])
        self.assertEqual(accepted, (0, 5, '字', 'その他'))
        self.assertEqual(reason, 'accepted')

    def test_new_repetition_is_rejected(self):
        self.assertEqual(self.check('かがみ', 'かかみ'), (None, 'new_repetition'))

    def test_punctuation_boundary_and_symbol_exception(self):
        out = C._check_replacement('め。', (0, 1, '。', '記号'), None, None)
        self.assertEqual(out, (None, 'new_punctuation'))
        out = C._check_replacement('めめ', (0, 2, '？？', '記号'), None, None)
        self.assertEqual(out, ((0, 2, '？？', '記号'), 'accepted'))

    def test_absorbed_span_is_the_returned_span(self):
        with patch.object(C, 'absorb_stray_char', return_value=(0, 3)):
            out = C._check_replacement('あいう', (0, 2, '文字', 'その他'), None, None)
        self.assertEqual(out, ((0, 3, '文字', 'その他'), 'accepted'))

    def test_reading_annotation_and_long_vowel_have_distinct_reasons(self):
        with patch.object(C, '_reading_spelled_in_bracket', return_value=True):
            self.assertEqual(self.check('よみ', '読み'), (None, 'reading_annotation'))
        with patch.object(C, 'long_vowel_protected_span', return_value='same word'):
            self.assertEqual(self.check('よみ', '読み'), (None, 'long_vowel'))

if __name__ == '__main__':
    unittest.main()
