# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import app,corrector as C,contextual_repair as Q,kango_tier as K
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NominalInflectionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))
    def test_native_anomaly_keeps_the_whole_word_search(self):
        self.assertTrue(Q._kana_grammar_boundary(self.tok('まとがい'),0,4))
        for text in ('やりがい','みます','まてがい'):
            with self.subTest(text=text):self.assertFalse(Q._kana_grammar_boundary(self.tok(text),0,len(text)))
        parts=self.tok('まとがい');parts[0]=parts[0][:5]+(False,)+parts[0][6:]
        self.assertFalse(Q._kana_grammar_boundary(parts,0,4))
        targets=Q.targets_for_line('まとがい',self.tok,self.a.store,self.a.dict_index)
        self.assertTrue(any(t.text=='まとがい' and t.boundary_kind=='lexical' and t.structural for t in targets))
    def test_generality_is_explicit_and_does_not_make_unknown_or_food_invalid(self):
        for word in ('間違い','誤り','ミス','エラー','勘違い','手違い'):
            with self.subTest(word=word):self.assertEqual(K.known_usage_tier(word),1)
        self.assertEqual(K.known_usage_tier('マテガイ'),2)
        self.assertIsNone(K.known_usage_tier('プネラルゴ'))
    def test_two_initial_stages_rank_meaning_before_bare_generality(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for text,expected in (('まとがい','間違い'),('まてがすをたべます。','マテガイをたべます。'),
                    ('まとがいをなおします。','間違いをなおします。'),
                    ('マテガイを食べます。','マテガイを食べます。'),
                    ('まてがいをたべます。','まてがいをたべます。'),
                    ('間違いを直します。','間違いを直します。'),('まちがい','まちがい'),
                    ('まとい','まとい'),('まがい','まがい'),('やりがい','やりがい'),
                    ('働きがい','働きがい'),('みます','みます'),('これをみます。','これをみます。'),
                    ('「まとがい」と入力します。','「まとがい」と入力します。')):
                with self.subTest(phase=phase,text=text):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    assert_reviewed_result_spelling(self, r, expected)
                    self.assertEqual(r.get('odd_spans'),[])
if __name__=='__main__':unittest.main()
