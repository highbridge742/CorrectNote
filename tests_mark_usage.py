# -*- coding: utf-8 -*-
"""Notation and short voices must survive every correction/normalization path."""
import unittest
from unittest.mock import patch
import morphology as M
import mark_usage as U
import literal_examples as L
import corrector as C


class MarkUsageTests(unittest.TestCase):
    def setUp(self):
        U.intentional_ranges.cache_clear()

    def tearDown(self):
        U.intentional_ranges.cache_clear()

    @staticmethod
    def predicate(base='叫ぶ', pos='動詞', known=True, start=0):
        return [M.Token('叫び',pos,base,'さけび',start,start+2,known,'自立','連用形')]

    def test_explicit_symbol_label_preserves_only_the_mark(self):
        for mark in ('゛','゜','\u3099','\u309a'):
            line='記号は'+mark+'です。'
            self.assertEqual(U.intentional_ranges(line),((3,4),))
        self.assertEqual(U.intentional_ranges('準備゜を確認します。'),())

    def test_vocal_shape_requires_a_native_voice_predicate(self):
        with patch.object(M,'tokenize',return_value=self.predicate()):
            for voice in ('あ゛ー','ン゛ー','う゛う゛','ガ゛ー'):
                self.assertEqual(U.intentional_ranges(voice+'と叫びます。'),((0,len(voice)),))
        for tokens in ([], self.predicate('確認する'), self.predicate(pos='名詞'),
                       self.predicate(known=False), self.predicate(start=1)):
            U.intentional_ranges.cache_clear()
            with patch.object(M,'tokenize',return_value=tokens):
                self.assertEqual(U.intentional_ranges('あ゛ーと叫びます。'),())

    def test_long_words_and_nonvocal_shapes_are_not_exempted(self):
        with patch.object(M,'tokenize',return_value=self.predicate()):
            for line in ('もじ゛つと叫ぶ','ケ゛イカクと叫ぶ','キーボード゛ーと叫ぶ',
                         '゛ーと叫ぶ','文字゛列を選ぶ','あ゛ーを選ぶ'):
                self.assertEqual(U.intentional_ranges(line),(),line)

    def test_vowel_voices_keep_quotations_and_line_endings(self):
        for line in ('あ゛ー！','う゛う゛','「う゛っ」と叫びました。','声は「あ゛ー」でした。'):
            ranges=U.intentional_ranges(line)
            self.assertTrue(ranges,line)
            self.assertTrue(all('゛' in line[a:b] for a,b in ranges))
        for line in ('う゛るを表示','あいう゛ーと入力','「あ゛列」'):
            self.assertEqual(U.intentional_ranges(line),(),line)

    def test_no_mark_needs_no_tokenization(self):
        with patch.object(M,'tokenize') as tokenize:
            self.assertEqual(U.intentional_ranges('普通に叫びます。'),())
            tokenize.assert_not_called()

    def test_composing_a_glyph_would_erase_its_explicit_description(self):
        self.assertEqual(U.intentional_ranges('は゜は半濁点を付けた形です。'),((0,2),))
        self.assertEqual(U.intentional_ranges('は゜を入力します。'),())

    def test_common_preservation_boundary_keeps_outside_edits_and_coordinates(self):
        line='甲あ゛ーと叫びました。乙'
        with patch.object(M,'tokenize',return_value=self.predicate()):
            result=C._with_literal_examples(lambda masked: dict(
                corrected=masked.replace('甲','甲甲').replace('乙','丙'),
                odd_spans=[],odd_reasons=[],unsure_spans=[]))(line)
        self.assertEqual(result['corrected'],'甲甲あ゛ーと叫びました。丙')
        for (a,b),(old,new,kind) in zip(result['original_spans'],result['details']):
            self.assertEqual(line[a:b],old)
        for (a,b),(old,new,kind) in zip(result['spans'],result['details']):
            self.assertEqual(result['corrected'][a:b],new)


if __name__=='__main__':
    unittest.main()
