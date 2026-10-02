# -*- coding: utf-8 -*-
"""Opaque original argument heads never supply generated words or meanings."""
import unittest
from unittest.mock import patch
import app,corrector as C,reading_segments as R,morphology as M,oddness as O
from tests_analysis_async import initial


@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class OpaquePreposedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def test_actual_case_and_same_completed_object_preserve_original_name(self):
        for text in ('ぷねらに資料を渡します。','ぴむねへ手紙を送ります。',
                'ぷねらと本を読みます。','ぷねらで資料を保存します。',
                'ぷねらにしりょうをわたします。','ぴむねへてがみをおくります。',
                'ぷねらとほんをよみます。','ぷねらでしりょうをほぞんします。'):
            with self.subTest(text=text):
                self.assertTrue(R._opaque_preposed_object_ranges(text))
                result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                    decisions=self.a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],text);self.assertFalse(result['odd_spans'])

    def test_a_separate_case_token_and_a_swallowed_case_share_the_same_boundary(self):
        self.assertIn((4,'に'),R._opaque_source_case_edges('ぷねらに資料を渡します',('に',)))
        self.assertIn((4,'を'),R._opaque_source_case_edges('ぷねらを読みます',('を',)))
        for text,case in (('ぷねらにおいを嗅ぎます','に'),
                          ('ぷねらとりを見ます','と'),('ぷねらでんきを使います','で')):
            with self.subTest(text=text):
                # Native best parsing swallows these entire kana noun runs.
                # Their possible case edge never completes the known object.
                self.assertFalse(R._opaque_preposed_object_ranges(text))
                native_tokenize=M.tokenize
                parts=[M.Token('ぷねら','名詞','ぷねら','',0,3,False,'一般')]
                parts.extend(M.Token(t.surface,t.pos,t.base_form,t.reading,t.start+3,t.end+3,
                    t.has_reading,t.pos_sub,t.infl_form) for t in native_tokenize(text[3:]))
                self.assertTrue(parts[1].has_reading)
                R._opaque_source_case_edges.cache_clear()
                try:
                    with patch.object(M,'tokenize',side_effect=lambda value:parts if value==text else native_tokenize(value)):
                        self.assertNotIn((4,case),R._opaque_source_case_edges(text,(case,)))
                finally:R._opaque_source_case_edges.cache_clear()

    def test_a_bad_or_open_known_predicate_supplies_no_source_protection(self):
        for text in ('ぷねらに資料を渡すます。','ぷねらへ手紙を送るます。',
                'ぷねらで資料を保存だました。','ぷねらに資料を渡し。',
                'ぷねらに資料を','ぷねらに','ぷねらに資料を眠ります。',
                'ゅしうに資料を渡します。','ぴっぁに資料を渡します。'):
            with self.subTest(text=text):
                self.assertFalse(R._opaque_preposed_object_ranges(text))

    def test_actual_written_object_and_action_meanings_cannot_be_borrowed(self):
        for text in ('ぷねらと飼料を読みます。','ぷねらに意見を繁栄します。',
                     'ぷねらに資料を眠ります。','ぷねらと資料を渡します。'):
            with self.subTest(text=text):
                self.assertFalse(R._opaque_preposed_object_ranges(text))
        self.assertTrue(R._opaque_preposed_object_ranges('ぷねらと資料を読みます。'))
        self.assertFalse(R._opaque_preposed_object_ranges('水に資料を渡します。'))

    def test_candidate_proof_and_original_final_validation_remain_distinct(self):
        text='ぷねらに資料を渡します。'
        self.assertFalse(R.native_surface_nominal_heads('ぷねら'))
        with patch.object(R,'source_opaque_object_ranges',side_effect=AssertionError('source-only exemption')):
            O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index)
        for start,end,new in ((0,3,'ぴむね'),(0,len(text),'ぴむねに資料を渡します。'),
                              (0,len(text),'ぷねらに手紙を渡します。')):
            with self.subTest(end=end,new=new):
                self.assertEqual(C._check_replacement(text,(start,end,new,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),)),
                    (None,'opaque_original_object'))

    def test_completed_prefix_and_independent_bad_clause_keep_separate_ownership(self):
        for text in ('あしたぷねらに資料を渡します。',
                     'ほぞんすればぴむねへ資料を送ります。'):
            with self.subTest(text=text):
                self.assertTrue(R.source_opaque_object_ranges(text))
        good='ぷねらに資料を渡します。';bad='資料を保存だました。'
        for text,edge in ((good+bad,len(good)),(bad+good,0)):
            result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                decisions=self.a.decisions,context_vec=None,input_method='kana')
            self.assertEqual(result['corrected'],text)
            self.assertTrue(result['odd_spans'])
            self.assertTrue(all(edge<=a<b<=edge+len(bad) for a,b in result['odd_spans']))


if __name__=='__main__':unittest.main()
