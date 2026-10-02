# -*- coding: utf-8 -*-
"""Known subject evidence cannot name an opaque original object or a candidate."""
import unittest
from unittest.mock import patch
import app,corrector as C,reading_segments as R,morphology as M,oddness as O
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class KnownSubjectOpaqueObjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def test_written_and_kana_subjects_keep_the_actual_finite_predicate(self):
        for text in ('先生がぴむねを読みます。','子どもがぷねらを書きます。',
                     'せんせいがぴむねをよみます。','この先生がぷねらを読みました。',
                     '先生がぴむねを説明します。','せんせいがぷねらをせつめいします。'):
            with self.subTest(text=text):
                self.assertTrue(R._known_subject_opaque_object_ranges(text))
                result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                    decisions=self.a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],text);self.assertFalse(result['odd_spans'])

    def test_case_meaning_and_completion_all_belong_to_the_original(self):
        for text in ('資料がぴむねを読みます。','先生がぷねらを眠ります。',
                     '先生がぴむねをよむます。','先生がぷねらを説明だました。',
                     '先生がぴむねを読み。','先生がぷねらを','先生がぷねらが読みます。',
                     '先生にぴむねを読みます。','ゅしうがぴむねを読みます。',
                     '先生がゅしうを読みます。','先生がぴっぁを読みます。',
                     '先生がぷねらを読まれます。'):
            with self.subTest(text=text):
                self.assertFalse(R._known_subject_opaque_object_ranges(text))

    def test_shared_adverbial_prefix_and_separate_bad_clause_keep_their_ranges(self):
        self.assertTrue(R.source_opaque_object_ranges('あした先生がぴむねを読みます。'))
        good='先生がぴむねを読みます。';bad='資料を保存だました。'
        for text,edge in ((good+bad,len(good)),(bad+good,0)):
            with self.subTest(first=bool(edge)):
                result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                    decisions=self.a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],text);self.assertTrue(result['odd_spans'])
                self.assertTrue(all(edge<=a<b<=edge+len(bad) for a,b in result['odd_spans']))

    def test_source_name_is_not_candidate_or_reading_evidence(self):
        text='先生がぴむねを読みます。'
        self.assertFalse(R.native_surface_nominal_heads('ぴむね'))
        with patch.object(R,'source_opaque_object_ranges',side_effect=AssertionError('source-only')):
            O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index)
        for replacement in ('先生がぷねらを読みます。','先生が資料を読みます。','学生がぴむねを読みます。'):
            with self.subTest(replacement=replacement):
                self.assertEqual(C._check_replacement(text,(0,len(text),replacement,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((0,len(text)),)),
                    (None,'opaque_original_object'))


if __name__=='__main__':unittest.main()
