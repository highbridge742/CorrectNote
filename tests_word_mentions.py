# -*- coding: utf-8 -*-
"""Explicit word mentions use native lexical evidence and original boundaries."""
import unittest
from unittest.mock import patch
import morphology as M
import literal_examples as L


class WordMentionTests(unittest.TestCase):
    def setUp(self):
        L._native_mentioned_word.cache_clear()
        L._native_inflected_form.cache_clear()

    def tearDown(self):
        self.setUp()

    @staticmethod
    def entries(surface):
        return {'エイ':(('名詞,一般,*,*','*','エイ','えい'),),
                'やや':(('副詞,一般,*,*','*','やや','やや'),),
                'すねる':(('動詞,自立,*,*','基本形','すねる','すねる'),),
                'ウン':(('感動詞,*,*,*','*','ウン','うん'),),
                '者':(('名詞,接尾,一般,*','*','者','しゃ'),)}.get(surface,())

    def test_explicit_word_labels_accept_native_nouns_verbs_and_adverbs(self):
        with patch.object(M,'dictionary_inflections',side_effect=self.entries):
            for word in ('エイ','やや','すねる'):
                for label in ('言葉','ことば','単語','語'):
                    line='「'+word+'」という'+label+'を説明します。'
                    with self.subTest(line=line):
                        self.assertEqual(L.protected_ranges(line),[(1,1+len(word))])

    def test_ordinary_quotation_and_label_prefixes_do_not_freeze_text(self):
        with patch.object(M,'dictionary_inflections',side_effect=self.entries):
            for line in ('「エイ」','「エイ」と書いた。','「エイ」という魚です。',
                         '「エイ」という言葉遣い','「エイ」という語形','「エイ」という語彙',
                         '「未知」という言葉','「者」という言葉'):
                with self.subTest(line=line):
                    self.assertEqual(L.protected_ranges(line),[])

    def test_exact_repeated_interjection_is_a_written_expression(self):
        with patch.object(M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('「ウンウン」という言葉'),[(1,5)])
            for line in ('「ウンエイ」という言葉','「エイエイ」という言葉'):
                self.assertEqual(L.protected_ranges(line),[])

    def test_unquoted_mention_keeps_original_coordinates(self):
        word=M.Token('エイ','名詞','エイ','えい',2,4,True,'一般')
        with patch.object(M,'tokenize',return_value=[word]),patch.object(
                M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('次にエイという単語を説明します。'),[(2,4)])

    def test_last_known_word_inside_an_unknown_compound_is_not_frozen(self):
        tokens=[M.Token('未知','名詞','未知','みち',0,2,True,'一般'),
                M.Token('エイ','名詞','エイ','えい',2,4,True,'一般')]
        with patch.object(M,'tokenize',return_value=tokens),patch.object(
                M,'dictionary_inflections',side_effect=self.entries):
            self.assertEqual(L.protected_ranges('未知エイという言葉'),[])

    def test_unclosed_or_mismatched_quote_is_not_an_unquoted_word(self):
        word=M.Token('エイ','名詞','エイ','えい',1,3,True,'一般')
        with patch.object(M,'tokenize',return_value=[word]),patch.object(
                M,'dictionary_inflections',side_effect=self.entries):
            for line in ('「エイという言葉','『エイ」という言葉'):
                self.assertEqual(L.protected_ranges(line),[])

    def test_missing_dictionary_does_not_turn_any_labeled_string_into_a_word(self):
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertEqual(L.protected_ranges('「がそぞう」という言葉'),[])


if __name__=='__main__':
    unittest.main()
