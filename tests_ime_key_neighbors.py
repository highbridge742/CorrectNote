# -*- coding: utf-8 -*-
"""Reuse original, already confirmed IME word edges in physical checks."""
import unittest
from unittest.mock import patch
import ime_inverse_gate as I

class CachedIMEKeyNeighborTests(unittest.TestCase):
    def query(self,confirmed=True,source='説明\t甲え乙\t参照',start=4,end=5,words=None):
        morph=('こうえおつ',words or ((0,1,0,2,100,3),(1,2,2,3,0,2),(2,3,3,5,100,3)))
        token=I._CORRECTION_CACHE.set({('first_match','甲え乙'):confirmed,('morph','甲え乙'):morph})
        try:
            with patch('ime_language.JapaneseIME') as api:
                result=I.cached_context_neighbors(source,start,end)
                api.assert_not_called();return result
        finally:I._CORRECTION_CACHE.reset(token)
    def test_uses_only_the_original_confirmed_field(self):
        self.assertEqual(self.query(),('こう','おつ'))
        self.assertIsNone(self.query(confirmed=False))
        self.assertIsNone(self.query(source='説明\t別え字\t参照'))
    def test_does_not_invent_a_boundary_inside_an_ime_word(self):
        self.assertIsNone(self.query(words=((0,2,0,3,100,3),(2,3,3,5,100,3))))
    def test_does_not_cross_an_example_column(self):
        self.assertIsNone(self.query(start=1,end=5))
    def test_no_cached_evidence_makes_no_native_query(self):
        token=I._CORRECTION_CACHE.set(None)
        try:
            with patch('ime_language.JapaneseIME') as api:
                self.assertIsNone(I.cached_context_neighbors('甲え乙',1,2));api.assert_not_called()
        finally:I._CORRECTION_CACHE.reset(token)
    def test_semantic_head_support_requires_a_whole_native_noun(self):
        from semantic_roles import retained_nominal_head_support as supports
        self.assertTrue(supports('片っ仮名','片仮名'))
        for original,candidate in (('片っ仮名','勝つがな'),('おくます','おくまい'),('資料か','資料'),('未字仮名','造語仮名')):
            with self.subTest(original=original,candidate=candidate):self.assertFalse(supports(original,candidate))

    def test_exact_source_reading_retains_first_match_for_key_checks(self):
        source='甲え乙';morph=('こうえおつ',((0,1,0,2,100,3),(1,2,2,3,0,2),(2,3,3,5,100,3)))
        for converted in (source,'別え字'):
            cache={};token=I._CORRECTION_CACHE.set(cache)
            try:
                with patch('ime_language.JapaneseIME') as api:
                    ime=api.return_value.__enter__.return_value
                    ime.available=True;ime.reverse_words.return_value=morph;ime.convert.return_value=converted
                    result=I.exact_context_reading(source,1,2)
                    self.assertEqual(cache['first_match',source],converted==source)
                    self.assertEqual(I.cached_context_neighbors(source,1,2),('こう','おつ') if converted==source else None)
                    self.assertEqual(I.exact_context_reading(source,1,2),result)
                    self.assertEqual(ime.convert.call_count,1)
                    self.assertEqual(ime.reverse_words.call_count,1)
            finally:I._CORRECTION_CACHE.reset(token)

if __name__=='__main__':unittest.main()