# -*- coding: utf-8 -*-
"""The candidate index and native nominal evidence may have different coverage."""
from tests_spelling_reference import assert_repaired_spelling
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
                assert_repaired_spelling(self, result, expected)
                self.assertEqual(result.get('odd_spans'),[])


    def test_existing_kana_anomaly_reaches_the_shared_object_interpretation(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('まとがいをなおします。','まとがいをたべます。'):
            targets=R.targets_for_line(text,tokenize,a.store,a.dict_index)
            nouns=[t for t in targets if t.boundary_kind=='nominal_object']
            self.assertEqual([(t.start,t.end) for t in nouns],[(0,4)])
            self.assertTrue(nouns[0].anomalies)
            self.assertIn(('まと','がい',0,4),nouns[0].anomalies)
            self.assertFalse(C._chunk_is_intact(nouns[0].text,tokenize,repair_context=nouns[0]))
        for text in ('まちがいをなおします。','まてがいをたべます。',
                     '葦原を眺めます。','ぷねらという名前です。',
                     '「まとがいをたべます」という誤入力例です。'):
            self.assertFalse([t for t in R.targets_for_line(text,tokenize,a.store,a.dict_index)
                              if t.boundary_kind=='nominal_object'],text)

    def test_candidate_meaning_uses_the_same_unchanged_predicate(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        # 2026-09-22: the explicit everyday-word judgment gives 間違い
        # the same usage tier as its kana spelling; native cost selects kanji.
        for source,expected in (('まとがいをなおします。','間違いをなおします。'),
                                 ('まとがいをたべます。','マテガイをたべます。'),
                                 ('まとがいをしゅうせいします。','間違いをしゅうせいします。'),
                                 ('まとがいをやきます。','マテガイをやきます。')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected, source)
            self.assertEqual(result.get('odd_spans'),[],source)

if __name__=='__main__':unittest.main()
