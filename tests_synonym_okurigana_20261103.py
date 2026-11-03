# -*- coding: utf-8 -*-
"""類語の送り仮名を元の語の活用の型へ（作った例・2026-11-03）。janome が要る。"""
import unittest
import synonyms as S
from morphology import HAS_JANOME


@unittest.skipUnless(HAS_JANOME, 'janome')
class Fit(unittest.TestCase):
    def fit(self, base, word):
        token = S._tokens(base)[0]
        readings = {S._hiragana(token.reading)} | set(S.load_table().readings(base) or ())
        return S._fit_verb(word, token, readings)

    def test_the_same_type_stays(self):
        self.assertEqual(self.fit('壊す', '崩す'), ('崩す', False))

    def test_a_pair_is_moved_to_the_type_of_the_word(self):
        self.assertEqual(self.fit('壊す', '倒れる'), ('倒す', False))

    def test_the_word_itself_is_dropped(self):
        self.assertEqual(self.fit('壊す', '壊れる'), (None, False))

    def test_same_reading_is_for_the_homophone_section(self):
        self.assertEqual(self.fit('放す', '離れる'), (None, False))

    def test_kana_of_the_same_root_is_dropped(self):
        self.assertEqual(self.fit('壊す', 'こわれる'), (None, False))

    def test_other_kana_of_another_type_goes_behind(self):
        self.assertEqual(self.fit('壊す', 'ぶつかる'), ('ぶつかる', True))

    def test_no_pair_goes_behind(self):
        self.assertEqual(self.fit('話す', '語る'), ('語る', True))

    def test_suru_verbs_stay(self):
        self.assertEqual(self.fit('壊す', '破壊する')[1], False)

    def test_ichidan_word_too(self):
        self.assertEqual(self.fit('倒れる', '倒す'), (None, False))


@unittest.skipUnless(HAS_JANOME and S.available(), 'table')
class Whole(unittest.TestCase):
    def flat(self, text):
        return [w for group in S.synonyms(text) for w in group]

    def test_every_listed_verb_keeps_the_tail_of_the_phrase(self):
        for text in ('壊している', '倒れた', '話します'):
            for word in self.flat(text):
                self.assertNotEqual(word, text)

    def test_the_tail_is_still_fitted(self):
        for word in self.flat('壊している'):
            self.assertTrue(word.endswith('ている') or word.endswith('でいる'), word)


if __name__ == '__main__':
    unittest.main()
