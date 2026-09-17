# -*- coding: utf-8 -*-
"""A word form being explained is different from ordinary quoted prose."""
import unittest
from unittest.mock import patch
import morphology as M
import literal_examples as L
import corrector as C


class WordformMentionTests(unittest.TestCase):
    def setUp(self):
        L._native_inflected_form.cache_clear()

    def tearDown(self):
        L._native_inflected_form.cache_clear()

    @staticmethod
    def forms(surface):
        if surface == '走ら':
            return (('動詞,自立,*,*', '未然形', '走る', 'はしら'),)
        return ()

    def test_native_form_and_explicit_label_are_both_required(self):
        with patch.object(M, 'dictionary_inflections', side_effect=self.forms):
            for label in ('語形', '活用形', '未然形', '言葉', 'ことば', '単語', '語'):
                line = '「走ら」という' + label + 'を示す。'
                self.assertEqual(L.protected_ranges(line), [(1, 3)])
            for line in ('「走ら」', '「走ら」と書いた。', '「走ら」という指示',
                         '「走ら」という言葉遣い', '「走ら」という語形論',
                         '「未知語」という語形', '「走ら」という語彙'):
                with self.subTest(line=line):
                    self.assertEqual(L.protected_ranges(line), [])

    def test_unquoted_form_uses_actual_token_coordinates(self):
        line = '次は走らという未然形を使う。'
        word = M.Token('走ら', '動詞', '走る', 'はしら', 2, 4, True, '自立', '未然形')
        with patch.object(M, 'tokenize', return_value=[word]), patch.object(
                M, 'dictionary_inflections', side_effect=self.forms):
            self.assertEqual(L.protected_ranges(line), [(2, 4)])

    def test_ordinary_text_needs_no_native_tokenizer(self):
        with patch.object(M, 'tokenize') as tokenize, patch.object(M, 'dictionary_inflections') as lookup:
            self.assertEqual(L.protected_ranges('走らの隣に文字を書く。'), [])
            tokenize.assert_not_called()
            lookup.assert_not_called()

    def test_absent_dictionary_does_not_invent_a_word_form(self):
        with patch.object(M, 'dictionary_inflections', return_value=None):
            self.assertEqual(L.protected_ranges('「走ら」という未然形を示す。'), [])

    def test_basic_form_or_noun_entry_alone_is_not_an_incomplete_form(self):
        for forms in ((('動詞,自立,*,*', '基本形', '走ら', 'はしら'),),
                      (('名詞,一般,*,*', '*', '走る', 'はしら'),)):
            L._native_inflected_form.cache_clear()
            with patch.object(M, 'dictionary_inflections', return_value=forms):
                self.assertEqual(L.protected_ranges('「走ら」という語形'), [])

    def test_only_last_token_of_a_predicate_is_not_frozen(self):
        parts = [M.Token('読ま', '動詞', '読む', 'よま', 0, 2, True, '自立', '未然形'),
                 M.Token('な', '助動詞', 'ない', 'な', 2, 3, True, '', 'ガル接続')]
        with patch.object(M, 'tokenize', return_value=parts), patch.object(
                M, 'dictionary_inflections', return_value=(('助動詞,*,*,*', 'ガル接続', 'ない', 'な'),)):
            self.assertEqual(L.protected_ranges('読まなという語形'), [])

    def test_unclosed_and_mismatched_quotes_are_not_unquoted_forms(self):
        for line in ('「走らという語形', '『走らという語形」'):
            word = M.Token('走ら', '動詞', '走る', 'はしら', 1, 3, True, '自立', '未然形')
            with patch.object(M, 'tokenize', return_value=[word]), patch.object(
                    M, 'dictionary_inflections', side_effect=self.forms):
                self.assertEqual(L.protected_ranges(line), [])

    def test_surrounding_edits_and_repeated_spelling_keep_their_positions(self):
        line = '甲「走ら」という語形と走らを比べる。'
        def engine(masked):
            return dict(corrected=masked.replace('甲', '甲甲').replace('走ら', '走れ'),
                        odd_spans=[], odd_reasons=[], unsure_spans=[])
        with patch.object(M, 'dictionary_inflections', side_effect=self.forms):
            result = C._with_literal_examples(engine)(line)
        self.assertEqual(result['corrected'], '甲甲「走ら」という語形と走れを比べる。')
        for (a, b), (old, new, category) in zip(result['original_spans'], result['details']):
            self.assertEqual(line[a:b], old)
        for (a, b), (old, new, category) in zip(result['spans'], result['details']):
            self.assertEqual(result['corrected'][a:b], new)


if __name__ == '__main__':
    unittest.main()
