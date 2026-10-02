# -*- coding: utf-8 -*-
"""Original opaque arguments keep actual case roles without becoming words."""
import unittest
import app,corrector as C,reading_segments as R,morphology as M
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class OpaqueCaseRolesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def test_unchanged_name_and_attested_case_keep_written_and_kana_predicates(self):
        for text in ('ぷねらに連絡します。','ぷねらへ行きます。','ぷねらで作業します。',
                     'ぷねらと話します。','ぴむねで食事した。','ぴむねで作業する。',
                     'ぷねらにれんらくします。','ぷねらへいきます。',
                     'ぷねらでさぎょうします。','ぷねらとはなします。'):
            with self.subTest(text=text):
                self.assertTrue(R._opaque_simple_object_ranges(text))
                result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                    decisions=self.a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],text);self.assertFalse(result['odd_spans'])

    def test_bad_open_or_wrong_case_predicate_cannot_supply_source_protection(self):
        for text in ('ぷねらに連絡だました。','ぷねらへ行くます。','ぷねらで作業するた。',
                     'ぷねらと話すます。','ぷねらで作業し。','ぷねらで作業',
                     'ぷねらに','ぷねらへ読みます。','ぷねらを眠ります。',
                     'ゅしうに連絡します。','ぴっぁで作業します。'):
            with self.subTest(text=text):self.assertFalse(R._opaque_simple_object_ranges(text))

    def test_known_following_object_keeps_its_own_semantic_proof(self):
        for text in ('ぷねらと飼料を読みます。','ぷねらに資料を眠ります。',
                     'ぷねらと資料を渡します。'):
            with self.subTest(text=text):self.assertFalse(R.source_opaque_object_ranges(text))
        self.assertTrue(R.source_opaque_object_ranges('ぷねらに資料を渡します。'))
        self.assertFalse(R.source_opaque_object_ranges('資料へ読みます。'))
        self.assertFalse(R.source_opaque_object_ranges('で作業します。'))

    def test_original_name_and_case_cannot_be_changed_by_a_broader_candidate(self):
        text='ぷねらで作業します。'
        self.assertFalse(R.native_surface_nominal_heads('ぷねら'))
        for start,end,new in ((0,3,'ぴむね'),(0,len(text),'ぴむねで作業します。'),
                              (0,len(text),'ぷねらに作業します。')):
            with self.subTest(new=new):
                self.assertEqual(C._check_replacement(text,(start,end,new,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),)),
                    (None,'opaque_original_object'))

    def test_proved_prefix_and_unrelated_bad_clause_keep_separate_ranges(self):
        for text in ('あしたぷねらに連絡します。','ほぞんすればぴむねで作業します。'):
            with self.subTest(text=text):self.assertTrue(R.source_opaque_object_ranges(text))
        good='ぷねらで作業します。';bad='資料を保存だました。'
        for text,edge in ((good+bad,len(good)),(bad+good,0)):
            result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                decisions=self.a.decisions,context_vec=None,input_method='kana')
            self.assertEqual(result['corrected'],text);self.assertTrue(result['odd_spans'])
            self.assertTrue(all(edge<=a<b<=edge+len(bad) for a,b in result['odd_spans']))

if __name__=='__main__':unittest.main()
