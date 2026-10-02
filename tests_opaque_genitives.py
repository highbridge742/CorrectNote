# -*- coding: utf-8 -*-
"""Unknown original genitives never supply candidate nouns or meanings."""
import unittest
from unittest.mock import patch
import app,corrector as C,reading_segments as R,morphology as M,oddness as O
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class OpaqueGenitiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def test_unknown_genitive_and_same_known_object_keep_text_without_purple(self):
        for text in ('ぴむねの本を読みます。','ぷねらの資料を保存します。',
                     'ぷねらの食事を作ります。','ぴむねの写真を見ます。',
                     'ぷねらのしりょうをほぞんします。','ぴむねのほんをよみます。'):
            with self.subTest(text=text):
                self.assertTrue(R._opaque_preposed_object_ranges(text))
                result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                    decisions=self.a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],text);self.assertFalse(result['odd_spans'])

    def test_unknown_left_does_not_complete_a_bad_or_unknown_known_frame(self):
        for text in ('ぷねらの飼料を読みます。','ぷねらの本を眠ります。',
                     'ぷねらの資料を保存だました。','ぷねらの資料を保存するた。',
                     'ぷねらの資料を保存しましょぅ。','ぷねらの資料を',
                     'ぷねらの','ぷねらので資料を読みます。','ぷねらのを読みます。',
                     'ゅしうの本を読みます。','ぴっぁの本を読みます。',
                     'ぷねらのぴむねを読みます。','先生の本を読みます。'):
            with self.subTest(text=text):self.assertFalse(R._opaque_preposed_object_ranges(text))
        # A single opaque whole nominal can still end in の. That does not
        # manufacture a genitive right-hand noun or prove a generated word.
        self.assertFalse(R.native_genitive_nominal_splits('ぷねらの',allow_unknown_left=True))

    def test_source_genitive_does_not_supply_candidate_evidence_or_changed_meaning(self):
        text='ぴむねの本を読みます。'
        self.assertFalse(R.native_surface_nominal_heads('ぴむね'))
        self.assertFalse(R.native_genitive_nominal_splits('ぴむねの本'))
        with patch.object(R,'source_opaque_object_ranges',side_effect=AssertionError('source-only exemption')):
            O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index)
        for start,end,new in ((0,3,'ぷねら'),(0,len(text),'ぷねらの本を読みます。'),
                              (0,len(text),'ぴむねの飼料を読みます。')):
            with self.subTest(new=new):
                self.assertEqual(C._check_replacement(text,(start,end,new,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),)),
                    (None,'opaque_original_object'))

    def test_same_prefix_and_independent_bad_clause_keep_their_boundaries(self):
        for text in ('しゅっぱつまえにぴむねの本を読みます。',
                     'ほぞんすればぷねらの資料を読みます。'):
            with self.subTest(text=text):self.assertTrue(R.source_opaque_object_ranges(text))
        good='ぴむねの本を読みます。';bad='資料を保存だました。'
        for text,edge in ((good+bad,len(good)),(bad+good,0)):
            result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                decisions=self.a.decisions,context_vec=None,input_method='kana')
            self.assertEqual(result['corrected'],text);self.assertTrue(result['odd_spans'])
            self.assertTrue(all(edge<=a<b<=edge+len(bad) for a,b in result['odd_spans']))

if __name__=='__main__':unittest.main()
