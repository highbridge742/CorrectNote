# -*- coding: utf-8 -*-
"""Opaque original subjects keep native case and actual unchanged voice."""
import unittest
from unittest.mock import patch
import app,corrector as C,reading_segments as R,morphology as M,oddness as O
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class OpaqueSubjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def test_same_nominative_and_finite_predicate_keep_written_and_kana_forms(self):
        for text in ('ぷねらが読みます。','ぴむねが眠ります。','ぷねらが届きます。',
                     'ぴむねが参加します。','ぷねらが動作します。','ぴむねがよみます。',
                     'ぷねらがさんかします。','ぴむねがどうさします。',
                     'ぷねらが参加した。','ぴむねが眠った。'):
            with self.subTest(text=text):
                self.assertTrue(R._opaque_simple_object_ranges(text))
                result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                    decisions=self.a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],text);self.assertFalse(result['odd_spans'])

    def test_explicit_object_still_owns_the_same_predicate(self):
        for text in ('ぷねらが資料を読みます。','ぴむねが手紙を書きます。',
                     'ぷねらが内容を説明します。','ぴむねがほんをよみます。',
                     'ぷねらがないようをせつめいします。'):
            with self.subTest(text=text):self.assertTrue(R._opaque_preposed_object_ranges(text))
        for text in ('ぷねらが飼料を読みます。','ぴむねが資料を眠ります。',
                     'ぷねらが内容を説明だました。'):
            with self.subTest(text=text):self.assertFalse(R.source_opaque_object_ranges(text))

    def test_voice_open_and_bad_connections_do_not_borrow_a_subject_role(self):
        for text in ('ぷねらが読まれます。','ぴむねが読ませます。','ぷねらがさんかされます。',
                     'ぴむねが眠るます。','ぷねらが参加するた。','ぴむねが参加し。',
                     'ぷねらが参加','ぴむねが','ゅしうが読みます。','ぴっぁが読みます。',
                     'ぷねらは読みます。','先生がが読みます。'):
            with self.subTest(text=text):self.assertFalse(R.source_opaque_object_ranges(text))

    def test_source_proof_assigns_no_person_role_or_generated_nominal(self):
        import semantic_roles as S
        text='ぷねらが読みます。'
        self.assertFalse(S.nominal_roles('ぷねら'))
        self.assertFalse(R.native_surface_nominal_heads('ぷねら'))
        with patch.object(R,'source_opaque_object_ranges',side_effect=AssertionError('source-only exemption')):
            O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index)
        for start,end,new in ((0,3,'ぴむね'),(0,len(text),'ぴむねが読みます。'),
                              (0,len(text),'ぷねらを読みます。')):
            with self.subTest(new=new):
                self.assertEqual(C._check_replacement(text,(start,end,new,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),)),
                    (None,'opaque_original_object'))

    def test_prefix_and_unrelated_malformed_clause_remain_separate(self):
        for text in ('しゅっぱつまえにぷねらが読みます。','ほぞんすればぴむねが参加します。'):
            with self.subTest(text=text):self.assertTrue(R.source_opaque_object_ranges(text))
        good='ぴむねが眠ります。';bad='資料を保存だました。'
        for text,edge in ((good+bad,len(good)),(bad+good,0)):
            result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                decisions=self.a.decisions,context_vec=None,input_method='kana')
            self.assertEqual(result['corrected'],text);self.assertTrue(result['odd_spans'])
            self.assertTrue(all(edge<=a<b<=edge+len(bad) for a,b in result['odd_spans']))

if __name__=='__main__':unittest.main()
