# -*- coding: utf-8 -*-
"""Recover readable predicates without guessing unknown text or changing offsets."""
import unittest
from unittest.mock import patch
import morphology as M


class UnknownClauseTests(unittest.TestCase):
    def source(self):
        text = 'しりょうをしらべいて'
        return text, [M.Token('しり','名詞','しり','しり',0,2,True,'一般'),
                      M.Token(text[2:],'名詞',text[2:],text[2:],2,len(text),False,'一般')]

    def tail(self):
        return [M.Token('しらべ','動詞','しらべる','しらべ',0,3,True,'自立','連用形'),
                M.Token('い','動詞','いる','い',3,4,True,'非自立','連用形'),
                M.Token('て','助詞','て','て',4,5,True,'接続助詞')]

    def test_known_object_and_predicate_restore_original_coordinates(self):
        text, source = self.source()
        with patch.object(M,'_nominal_reading_evidence',side_effect=lambda s:s=='しりょう'), \
             patch.object(M,'_tokenize_janome',return_value=self.tail()):
            result = M._restore_unknown_predicates(text,source)
        self.assertEqual(''.join(t.surface for t in result),text)
        self.assertEqual([(t.surface,t.start,t.end) for t in result],
                         [('しりょう',0,4),('を',4,5),('しらべ',5,8),('い',8,9),('て',9,10)])
        self.assertTrue(all(text[t.start:t.end]==t.surface for t in result))
        self.assertEqual(result[2].base_form,'しらべる')
        self.assertEqual(result[2].infl_form,'連用形')

    def test_no_unknown_text_means_no_second_analysis(self):
        source=self.tail()
        with patch.object(M,'_tokenize_janome') as analyze:
            self.assertIs(M._restore_unknown_predicates('しらべいて',source),source)
        analyze.assert_not_called()

    def test_unknown_object_is_not_declared_to_be_a_dictionary_word(self):
        text,source=self.source()
        with patch.object(M,'_nominal_reading_evidence',return_value=False), \
             patch.object(M,'_tokenize_janome',return_value=[]) as analyze:
            self.assertEqual(M._restore_unknown_predicates(text,source),source)
        self.assertEqual([call.args[0] for call in analyze.call_args_list],['しりょう'])

    def test_unreadable_or_nominal_tail_does_not_establish_predicate_boundary(self):
        text,source=self.source()
        bad=[M.Token('しらべいて','名詞','しらべいて','しらべいて',0,5,False,'一般')]
        for tail in (bad,[M.Token('しらべいて','名詞','しらべいて','しらべいて',0,5,True,'一般')]):
            with self.subTest(tail=tail),patch.object(M,'_nominal_reading_evidence',return_value=True), \
                 patch.object(M,'_tokenize_janome',return_value=tail):
                self.assertEqual(M._restore_unknown_predicates(text,source),source)

    def test_surface_without_verbal_ending_is_not_a_clause(self):
        text,source=self.source()
        tail=[M.Token('しらべいて','動詞','しらべいて','しらべいて',0,5,True,'自立','基本形')]
        with patch.object(M,'_nominal_reading_evidence',return_value=True), \
             patch.object(M,'_tokenize_janome',return_value=tail):
            self.assertEqual(M._restore_unknown_predicates(text,source),source)

    def test_modifier_keeps_its_pos_and_absolute_coordinates(self):
        body='このあたらしいしりょうをしらべいて'
        text='先頭：'+body+'。'
        prefix=[M.Token('この','連体詞','この','この',0,2,True),
                M.Token('あたらしい','形容詞','あたらしい','あたらしい',2,7,True,'自立','基本形')]
        source=[M.Token('先頭','名詞','先頭','せんとう',0,2,True,'一般'),
                M.Token('：','記号','：','：',2,3,False),
                M.Token(body,'名詞',body,body,3,3+len(body),False,'一般'),
                M.Token('。','記号','。','。',3+len(body),len(text),False)]
        with patch.object(M,'_nominal_reading_evidence',side_effect=lambda s:s=='しりょう'), \
             patch.object(M,'_tokenize_janome',side_effect=lambda s:self.tail() if s=='しらべいて' else prefix):
            result=M._restore_unknown_predicates(text,source)
        self.assertEqual(''.join(t.surface for t in result),text)
        self.assertEqual([(t.surface,t.pos,t.start,t.end) for t in result[2:5]],
                         [('この','連体詞',3,5),('あたらしい','形容詞',5,10),('しりょう','名詞',10,14)])
        self.assertTrue(all(text[t.start:t.end]==t.surface for t in result))

    def test_unknown_or_verbal_modifier_does_not_become_a_nominal_prefix(self):
        for token in (M.Token('この','連体詞','この','この',0,2,False),
                      M.Token('かく','動詞','かく','かく',0,2,True,'自立','基本形'),
                      M.Token('よく','形容詞','よい','よく',0,2,True,'自立','連用テ接続')):
            with self.subTest(token=token),patch.object(M,'_nominal_reading_evidence',side_effect=lambda s:s=='しりょう'), \
                 patch.object(M,'_tokenize_janome',return_value=[token]):
                self.assertEqual(M._nominal_reading_tokens(token.surface+'しりょう'),[])

    def test_symbol_or_space_does_not_join_unknown_fragments(self):
        for text in ('しりょうを しらべいて','しりょうを・しらべいて','シリョウヲシラベイテ'):
            source=[M.Token(text,'名詞',text,text,0,len(text),False,'一般')]
            with self.subTest(text=text),patch.object(M,'_nominal_reading_evidence') as lookup:
                self.assertEqual(M._restore_unknown_predicates(text,source),source)
            lookup.assert_not_called()

    def test_excessive_unknown_run_is_bounded(self):
        text='あ'*81
        source=[M.Token(text,'名詞',text,text,0,len(text),False,'一般')]
        with patch.object(M,'_nominal_reading_evidence') as lookup:
            self.assertEqual(M._restore_unknown_predicates(text,source),source)
        lookup.assert_not_called()


if __name__=='__main__':
    unittest.main()
