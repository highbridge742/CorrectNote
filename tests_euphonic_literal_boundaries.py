# -*- coding: utf-8 -*-
"""Generated predicates and literal examples keep their grammatical boundaries."""
import unittest
from unittest.mock import patch
import morphology as M
import contextual_repair as R
import literal_examples as L


class EuphonicLiteralBoundaryTests(unittest.TestCase):
    def setUp(self):
        R._productive_predicate.cache_clear()
        R._modern_te_allowed.cache_clear()
        L._native_mentioned_word.cache_clear()
        L._native_inflected_form.cache_clear()

    def tearDown(self):
        self.setUp()

    def predicate(self,head,reading,kind,form,lemma,ending):
        parts=[M.Token(head,'動詞',lemma,reading,0,len(head),True,'自立',form),
               M.Token(ending,'助動詞',ending[0],ending,len(head),len(head)+len(ending),True,'','仮定形')]
        paradigms=(('動詞,自立,*,*',kind,form,lemma,reading),)
        with patch.object(M,'tokenize',return_value=parts), \
             patch.object(M,'dictionary_paradigms',return_value=paradigms), \
             patch('oddness.aspect_auxiliary_needs_te',return_value=False):
            return R._productive_predicate(head+ending,head)

    def test_generated_conditional_rejects_non_euphonic_godan_stem(self):
        self.assertFalse(self.predicate('割り','わり','五段・ラ行','連用形','割る','たら'))
        self.assertTrue(self.predicate('割っ','わっ','五段・ラ行','連用タ接続','割る','たら'))

    def test_generated_voiced_conditional_uses_verb_paradigm(self):
        self.assertTrue(self.predicate('泳い','およい','五段・ガ行','連用タ接続','泳ぐ','だら'))
        self.assertFalse(self.predicate('泳い','およい','五段・ガ行','連用タ接続','泳ぐ','たら'))

    def test_s_and_ichidan_continuatives_keep_their_normal_conditional(self):
        self.assertTrue(self.predicate('話し','はなし','五段・サ行','連用形','話す','たら'))
        self.assertTrue(self.predicate('食べ','たべ','一段','連用形','食べる','たら'))

    def test_noun_and_classical_auxiliary_do_not_prove_a_modern_past_link(self):
        self.assertIsNone(R._modern_euphonic_link('たら','名詞:一般'))
        self.assertIsNone(R._modern_euphonic_link('たら','助動詞','未然形'))
        self.assertIsNone(R._modern_euphonic_link('たり','助動詞','基本形'))
        self.assertEqual(R._modern_euphonic_link('だり','助詞:並立助詞'),'だ')

    @staticmethod
    def entries(surface):
        return {'く':(('動詞,非自立,*,*','基本形','く','く'),),
                'けれ':(('助動詞,*,*,*','仮定形','けり','けれ'),),
                '書く':(('動詞,自立,*,*','基本形','書く','かく'),),
                '未知甲書く':()}.get(surface,())

    def test_unknown_leading_piece_cannot_leave_only_a_known_final_verb_frozen(self):
        tokens=[M.Token('未知甲','名詞','未知甲','未知甲',0,3,False,'一般'),
                M.Token('書く','動詞','書く','かく',3,5,True,'自立','基本形')]
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('未知甲書くという言葉'),[])

    def test_bound_verb_after_a_noun_is_not_a_free_literal_word(self):
        tokens=[M.Token('語','名詞','語','ご',0,1,True,'一般'),
                M.Token('く','動詞','く','く',1,2,True,'非自立','基本形')]
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('語くという言葉'),[])

    def test_inflected_form_after_an_unknown_piece_has_no_established_left_boundary(self):
        tokens=[M.Token('未知甲','名詞','未知甲','未知甲',0,3,False,'一般'),
                M.Token('けれ','助動詞','けり','けれ',3,5,True,'','仮定形')]
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('未知甲けれという活用形'),[])

    def test_space_and_explicit_quote_establish_the_actual_word_boundary(self):
        tokens=[M.Token('未知甲','名詞','未知甲','未知甲',0,3,False,'一般'),
                M.Token('書く','動詞','書く','かく',4,6,True,'自立','基本形')]
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('未知甲 書くという言葉'),[(4,6)])
        with patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('「く」という言葉'),[(1,2)])

    def test_auxiliary_after_a_known_nominal_piece_is_not_an_independent_form(self):
        tokens=[M.Token('甲','名詞','甲','こう',0,1,True,'一般'),
                M.Token('けれ','助動詞','けり','けれ',1,3,True,'','仮定形')]
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('甲けれという活用形'),[])


if __name__=='__main__':
    unittest.main()
