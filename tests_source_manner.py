# -*- coding: utf-8 -*-
"""Repairing a malformed verb must retain its actual native manner form."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import corrector as C


@unittest.skipUnless(M.dictionary_inflections('薄く'),'requires native dictionary')
class SourceMannerTests(unittest.TestCase):
    def test_source_object_and_actual_native_adjective_supply_the_range(self):
        text='たまねぎをうすくくきります。'
        self.assertEqual(R.native_predicate_modifier_ranges(text),((5,8),))
        self.assertIn((5,8),R.native_context_ranges(text))
        self.assertTrue(R.preserves_native_predicate_modifier(text,'たまねぎをうすくきります。'))
        self.assertFalse(R.preserves_native_predicate_modifier(text,'たまねぎをうかくくきります。'))
        self.assertEqual(R.native_predicate_modifier_ranges('ぷねらをうすくくきります。'),())
        self.assertEqual(R.native_predicate_modifier_ranges('たまねぎをうすいくきります。'),())

    def test_common_final_check_distinguishes_modifier_and_duplicate_guards(self):
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='たまねぎをうすくくきります。'
        for candidate,reason in (('うかくくきります','completed_predicate_modifier'),
                                 ('うすくきります','duplicate_repair_disabled')):
            with self.subTest(candidate=candidate):
                result,why=C._check_replacement(text,(5,13,candidate,'かな入力'),
                    a.store,tokenize,a.dict_index,a.decisions)
                self.assertIsNone(result)
                self.assertEqual(why,reason)

    def test_forbidden_duplicate_does_not_reroute_into_a_changed_adjective(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        text='たまねぎをうすくくきります。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],text)
        self.assertTrue(result.get('odd_spans'))
        text='たまねぎをうすくきくります。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, 'たまねぎをうすくきります。')
        self.assertEqual(result.get('odd_spans'),[])


    def test_native_manner_meaning_survives_an_outer_unknown_parse(self):
        import semantic_roles as S
        before='たまねぎとにんじんを'
        for action in ('こまかくきります','こまかくおくります'):
            proof=S.candidate_evidence('にんじん',action,'',before=before)
            self.assertTrue(proof and proof['shared_roles'],action)
        self.assertIsNone(S.candidate_evidence('未分類語','こまかくきります','',before=before))
        self.assertFalse((S.candidate_evidence('意味','こまかくきります','',before='意味を') or {}).get('shared_roles'))


if __name__=='__main__':unittest.main()
