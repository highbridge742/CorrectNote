# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,pos_grammar as G
from tests_analysis_async import initial
from last_choice import set_active

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class CoordinatedGrammarDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=initial()
    @classmethod
    def tearDownClass(cls):set_active(None)
    def marked(self,text):return G.odd_kana_spans(text,self.a.dict_index,self.a.store)
    def test_original_syntax_clears_only_the_fragment_mark(self):
        for text in ('器用と不器用とにわけます','有名と無名とにわけます','赤と白とにわけます'):
            with self.subTest(text=text):
                self.assertEqual(R.native_coordinated_syntax_ranges(text),((0,len(text)),))
                self.assertFalse(self.marked(text+'。'))
                self.assertIsNone(R.native_coordinated_case_cut(text))
                self.assertEqual(R.native_source_predicate_ranges(text),())
                with patch.object(R,'native_coordinated_syntax_ranges',return_value=()):
                    self.assertTrue(self.marked(text+'。'))
    def test_each_existing_member_conflict_keeps_the_original_mark(self):
        for text in ('野菜と精度とをたべます','野菜と資料とをたべます','資料と野菜とをたべます'):
            with self.subTest(text=text):
                self.assertEqual(R.native_coordinated_syntax_ranges(text),())
                self.assertIsNone(R.native_coordinated_case_cut(text,grammar_only=True))
                self.assertEqual(self.marked(text+'。'),[(5,11)])
    def test_known_good_meaning_retains_the_existing_source_proof(self):
        text='野菜と果物とをたべます'
        self.assertEqual(R.native_coordinated_case_cut(text),7)
        self.assertEqual(R.native_source_predicate_ranges(text),((0,len(text)),))
        self.assertFalse(self.marked(text+'。'))
    def test_missing_meaning_is_not_a_new_candidate_permission(self):
        import semantic_roles as S
        text='器用と不器用とにわけます'
        with patch.object(S,'candidate_evidence',return_value=None):
            self.assertEqual(R.native_coordinated_case_cut.__wrapped__(text,grammar_only=True),8)
            self.assertIsNone(R.native_coordinated_case_cut.__wrapped__(text))
    def test_actual_coordination_and_case_dictionary_evidence_are_required(self):
        text='器用と不器用とにわけます';lookup=M.dictionary_inflections
        with patch.object(M,'dictionary_inflections',side_effect=lambda value:
                () if value in ('と','に') else lookup(value)):
            self.assertIsNone(R.native_coordinated_case_cut.__wrapped__(text,grammar_only=True))
        with patch.object(R,'native_written_nominal_coordination',return_value=()),patch.object(R,'native_coordinated_nominal_parts',return_value=()):
            self.assertIsNone(R.native_coordinated_case_cut.__wrapped__(text,grammar_only=True))
    def test_unfinished_or_unattested_predicate_does_not_borrow_completion(self):
        for text in ('器用と不器用とにわけ','器用と不器用とにぷねら','器用と不器用とにわけますです','器用と不器用とに'):
            with self.subTest(text=text):self.assertEqual(R.native_coordinated_syntax_ranges(text),())
        for text in ('器用とにいきます','昼夜とにわけます'):
            with self.subTest(text=text):self.assertIsNone(R.native_coordinated_case_cut(text,grammar_only=True))
    def test_ranges_do_not_certify_a_following_error_or_other_column(self):
        for separator in ('。','\t','\n'):
            text='器用と不器用とにわけます'+separator+'資料をに入れます'
            with self.subTest(separator=separator):
                self.assertEqual(R.native_coordinated_syntax_ranges(text),((0,12),))
        self.assertEqual(R.native_coordinated_syntax_ranges('器用と不器用とにわけて資料をのみます'),())
    def test_body_keeps_text_and_the_independent_anomaly(self):
        import correction_entry as A
        a=self.a
        for text,odd in [('器用と不器用とにわけます。',[]),
                ('器用と不器用とにわけます。資料をに入れます。',[(15,17)]),
                ('野菜と精度とをたべます。',[(5,11)]),
                ('「器用と不器用とにわけます」という文字列です。',[])]:
            with self.subTest(text=text):
                r=A.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],odd);self.assertEqual(r['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
