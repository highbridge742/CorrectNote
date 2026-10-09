# -*- coding: utf-8 -*-
"""A necessary native end position never replaces a complete source proof."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.HAS_JANOME,'Requires native dictionary')
class NativeSequenceEndPositionsTests(unittest.TestCase):
    def tearDown(self):
        R.completed_native_reading_sequence.cache_clear()

    def test_finite_literary_copula_and_recovered_suffixes_remain_possible(self):
        for text in ('よむ','おおきい','げんきだ','げんきだった',
                     'ありし','よみける','せし','かきし','かった',
                     'としょかんでかりた','みせでかった',
                     'しりょうをほぞんした','しりょうをかくにんした'):
            with self.subTest(text=text):
                self.assertTrue(R.native_attributive_predicate_end(text))
                self.assertIn(len(text),R._native_attributive_end_positions(text))

    def test_positions_come_only_from_nonempty_original_dictionary_prefixes(self):
        def forms(tail):
            if tail=='あいうえ':
                return (('', '動詞,自立,','五段','基本形','', ''),
                        ('あいうえお','動詞,自立,','五段','基本形','', ''),
                        ('ぷねら','助動詞,','文語','連体形','', ''),
                        ('あい','名詞,一般,','*','基本形','', ''),
                        ('あ','動詞,自立,','五段','連用形','', ''))
            if tail=='いうえ':return (('い','動詞,自立,','五段','基本形','い','ぷねら'),)
            if tail=='うえ':return (('うえ','助動詞,','文語','体言接続','うえ','うえ'),)
            return ()
        with patch.object(M,'dictionary_prefix_paradigms',side_effect=forms):
            self.assertEqual(R._native_attributive_end_positions('あいうえ'),frozenset((2,4)))
            self.assertEqual(R._native_attributive_end_positions(''),frozenset())

    def test_unavailable_dictionary_preserves_exhaustive_fallback(self):
        def forms(tail):
            return None if tail=='いう' else (('あ','動詞,自立,','五段','基本形','あ','あ'),)
        with patch.object(M,'dictionary_prefix_paradigms',side_effect=forms):
            self.assertIsNone(R._native_attributive_end_positions('あいう'))
        with patch.object(R,'_native_attributive_end_positions',return_value=None):
            self.assertTrue(R.completed_native_reading_sequence('としょかんでかりたほんをかえします'))
            self.assertFalse(R.completed_native_reading_sequence('ぷねらでかりたほんをかえします'))

    def test_possible_position_does_not_certify_reading_grammar_or_meaning(self):
        for text in ('ぷねらでかりたほんをかえします','としょかんでかりますほんをかえします',
                     'としょかんでかりたへいわをかえします','としょかんでかりほんをかえします'):
            R.completed_native_reading_sequence.cache_clear()
            # Even fabricated broad positions cannot replace the unchanged
            # dictionary reading, attributive grammar and both noun roles.
            with patch.object(R,'_native_attributive_end_positions',return_value=frozenset(range(len(text)+1))):
                self.assertFalse(R.completed_native_reading_sequence(text),text)
        R.completed_native_reading_sequence.cache_clear()
        with patch.object(R,'native_attributive_predicate_end',return_value=False):
            self.assertFalse(R.completed_native_reading_sequence('としょかんでかりたほんをかえします'))

    def test_wrong_prefix_reading_cannot_supply_a_complete_source_proof(self):
        original=R._native_attributive_end_positions
        def untrusted_positions(text):
            def forms(tail):
                return ((tail[:1],'動詞,自立,','五段','基本形',tail[:1],'ぷねら'),)
            # Only the necessary-condition query sees the wrong readings.
            # The actual source and its existing dictionary proof stay real.
            with patch.object(M,'dictionary_prefix_paradigms',side_effect=forms):
                return original(text)
        with patch.object(R,'_native_attributive_end_positions',side_effect=untrusted_positions):
            self.assertFalse(R.completed_native_reading_sequence('ぷねらでかりたほんをかえします'))
            self.assertFalse(R.completed_native_reading_sequence('としょかんでかりますほんをかえします'))
            self.assertTrue(R.completed_native_reading_sequence('としょかんでかりたほんをかえします'))


if __name__=='__main__':unittest.main()
