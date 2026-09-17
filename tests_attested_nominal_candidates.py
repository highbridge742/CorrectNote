# -*- coding: utf-8 -*-
"""The candidate index and native nominal evidence may have different coverage."""
import unittest
import morphology as M
import contextual_repair as R


@unittest.skipUnless(M.dictionary_inflections('筆'),'requires native dictionary')
class AttestedNominalCandidateTests(unittest.TestCase):
    def test_an_empty_search_index_does_not_hide_an_attested_ordinary_noun(self):
        class EmptyIndex:
            def surfaces_for_reading(self,*args,**kwargs):return []
            def inflected_surfaces_for_reading(self,*args,**kwargs):return []
        class EmptyVocabulary:
            def lookup(self,*args):return []
        self.assertIn('筆',R._surfaces('ふで',EmptyVocabulary(),EmptyIndex()))
        self.assertEqual(R._surfaces('ふでしらゆほ',EmptyVocabulary(),EmptyIndex()),[])

    def test_native_candidate_repairs_the_context_and_keeps_the_normal_spelling(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (('ぬでをにほんあらいます。','筆をにほんあらいます。'),
                                 ('ふでをにほんあらいます。','ふでをにほんあらいます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
