# -*- coding: utf-8 -*-
"""An opaque topic keeps its known object's finite predicate and source identity."""
import unittest
from unittest.mock import patch
import app,corrector as C,reading_segments as R,morphology as M,oddness as O
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class OpaqueTopicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def correct(self,text):
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None,input_method='kana')

    def test_unchanged_topic_with_its_same_known_object(self):
        for text in ('ぷねらは資料を読みました。','ぴむねは手紙を書きます。',
                     'ぷねらは内容を説明します。','ぷねらは資料を読みます。',
                     'ぴむねはしりょうをほぞんします。'):
            with self.subTest(text=text):
                self.assertTrue(R.source_opaque_object_ranges(text))
                result=self.correct(text)
                self.assertEqual(result['corrected'],text);self.assertFalse(result['odd_spans'])

    def test_same_written_meaning_and_finite_voice_remain_required(self):
        for text in ('ぷねらは資料を食べました。','ぷねらは飼料を読みます。',
                     'ぷねらは資料を保存するた。','ぷねらは資料を保存だました。',
                     'ぷねらは資料を読まれます。','ぷねらは資料を読ませます。',
                     'ぷねらは資料を読み。','ぷねらは資料を','ぷねらは読みます。',
                     'ぷねらも資料を読みます。','ゅしうは資料を読みます。',
                     '先生はは資料を読みます。','先生がは資料を読みます。'):
            with self.subTest(text=text):self.assertFalse(R.source_opaque_object_ranges(text))

    def test_topic_is_source_evidence_not_a_named_or_generated_subject(self):
        text='ぷねらは資料を読みます。'
        self.assertFalse(R.native_surface_nominal_heads('ぷねら'))
        with patch.object(R,'source_opaque_object_ranges',side_effect=AssertionError('source-only evidence')):
            O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index)
        for start,end,value in ((0,3,'ぴむね'),(0,len(text),'ぷねらが資料を読みます。'),
                                (0,len(text),'ぷねらは手紙を読みます。')):
            with self.subTest(value=value):
                self.assertEqual(C._check_replacement(text,(start,end,value,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),)),
                    (None,'opaque_original_object'))

    def test_prefix_and_independent_bad_clause_keep_separate_scope(self):
        self.assertTrue(R.source_opaque_object_ranges('ほぞんすればぷねらは資料を読みます。'))
        good='ぷねらは資料を読みます。';bad='資料を保存だました。'
        for text,edge in ((good+bad,len(good)),(bad+good,0)):
            result=self.correct(text)
            self.assertEqual(result['corrected'],text);self.assertTrue(result['odd_spans'])
            self.assertTrue(all(edge<=a<b<=edge+len(bad) for a,b in result['odd_spans']))

if __name__=='__main__':unittest.main()
