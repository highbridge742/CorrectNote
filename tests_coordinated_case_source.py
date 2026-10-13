# -*- coding: utf-8 -*-
"""Original coordinated nouns retain their final case and complete predicate."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import corrector as C
import pos_grammar as P
from tests_analysis_async import initial
from last_choice import set_active

@unittest.skipUnless(M.dictionary_inflections('父'),'requires native dictionary')
class CoordinatedCaseSourceTests(unittest.TestCase):
    def test_actual_members_case_and_complete_predicate(self):
        for text,cut in (('布と紙とをきります',5),('野菜と果物とをたべます',7)):
            with self.subTest(text=text):
                self.assertEqual(R.native_coordinated_case_cut(text),cut)
                self.assertIn((0,len(text)),R.native_source_predicate_ranges(text))
        self.assertIsNone(R.native_coordinated_case_cut('器用とにいきます'))
        self.assertIsNone(R.native_coordinated_case_cut('昼夜とにわけます'))

    def test_missing_member_and_unfinished_tail_do_not_borrow_completion(self):
        for text in ('父とぷねらとにいきます','ぷねらと母とにいきます',
                     '父と母とにいきましただ','父と母とにぷねら','父と母とにいきま',
                     '父と母とに','父と母とにわけましただ'):
            self.assertNotIn((0,len(text)),R.native_source_predicate_ranges(text),text)
        for text in ('父と母とに わけます','父と母とに\tわけます',
                     '父と母とに。わけます','父と母とに「わけます」'):
            # The range owner splits clauses before supplying the nominal cut.
            self.assertNotIn((0,len(text)),R.native_source_predicate_ranges(text),text)

    def test_unchanged_grammar_cannot_override_independent_conflict(self):
        text='野菜と果物とをたべます'
        with patch.object(R,'_native_written_predicate_conflicts',return_value=True):
            self.assertNotIn((0,len(text)),R.native_source_predicate_ranges.__wrapped__(text))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertIsNone(R.native_coordinated_case_cut.__wrapped__(text))
        with patch.object(R,'native_written_nominal_coordination',return_value=()), \
             patch.object(R,'native_coordinated_nominal_parts',return_value=()):
            self.assertIsNone(R.native_coordinated_case_cut.__wrapped__(text))

    def test_every_original_member_must_fit_the_same_predicate(self):
        for text in ('野菜と精度とをたべます','野菜と資料とをたべます',
                     '精度と野菜とをたべます','資料と野菜とをたべます',
                     '器用と不器用とにわけます','父と母とにいきます'):
            self.assertIsNone(R.native_coordinated_case_cut(text),text)
            self.assertNotIn((0,len(text)),R.native_source_predicate_ranges(text),text)

    def test_shared_original_range_reaches_correction_entry_and_purple(self):
        a=initial();source='野菜と果物とをたべます。';tok=C.make_tokenizer(a.store)
        token=C._CORRECTION_SOURCE.set(source)
        try:
            self.assertTrue(C._chunk_is_intact('とをたべます',tok))
            self.assertEqual(P.odd_kana_spans(source,a.dict_index,a.store),[])
            prefix='資料。';joined=prefix+source
            self.assertIn((len(prefix),len(prefix)+len(source)-1),R.native_context_ranges(joined))
        finally:C._CORRECTION_SOURCE.reset(token);set_active(None)

    def test_full_entry_keeps_incompatible_member_unconverted(self):
        import correction_entry as A
        for source in ('野菜と精度とをたべます。','資料と野菜とをたべます。'):
            a=initial()
            try:
                result=A.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['odd_spans'],[(5,11)])
                self.assertEqual(result['analysis_status'],'complete')
            finally:set_active(None)

    def test_independent_case_error_remains_outside_the_proved_clause(self):
        import correction_entry as A
        a=initial();source='野菜と果物とをたべます。資料をに入れます。'
        try:
            result=A.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],'野菜と果物とを食べます。資料をに入れます。')
            self.assertEqual(result['odd_spans'],[(14,16)])
            self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_initial_entry_preserves_members_and_reports_complete(self):
        import correction_entry as A
        for source,expected in (('野菜と果物とをたべます。','野菜と果物とを食べます。'),('布と紙とをきります。','布と紙とをきります。')):
            a=initial()
            try:
                result=A.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
                self.assertEqual(result['analysis_status'],'complete')
            finally:set_active(None)

if __name__=='__main__':unittest.main()
