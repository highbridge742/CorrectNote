# -*- coding: utf-8 -*-
"""A range shrunk inside a word keeps the word's reading, so its homophones are offered (2026-11-03)."""
import unittest
from unittest import mock

import units
from units import _fragment_reading, make_range_unit


class Fragment(unittest.TestCase):
    def test_cut_by_the_kana_tail(self):
        self.assertEqual(_fragment_reading('走っている', 'はしっている', 0, 3), 'はしって')
        self.assertEqual(_fragment_reading('走っている', 'はしっている', 0, 2), 'はしっ')

    def test_the_tail_of_a_word(self):
        self.assertEqual(_fragment_reading('走っている', 'はしっている', 2, 5), 'ている')

    def test_katakana_reading(self):
        self.assertEqual(_fragment_reading('走って', 'ハシッテ', 0, 2), 'はしっ')

    def test_inside_a_kanji_run_nothing_is_guessed(self):
        self.assertEqual(_fragment_reading('会議', 'かいぎ', 0, 1), '')

    def test_no_reading(self):
        self.assertEqual(_fragment_reading('走って', '', 0, 2), '')

    def test_a_reading_that_does_not_fit(self):
        self.assertEqual(_fragment_reading('走って', 'かかか', 0, 2), '')


class RangeUnit(unittest.TestCase):
    def word(self, text, reading):
        return dict(text=text, base=text, reading=reading, start=0, end=len(text), kind='plain')

    def unit(self, line, words, start, end):
        with mock.patch('morphology.native_tokens_in_span', return_value=()):
            return make_range_unit(line, words, start, end)

    def test_shrunk_inside_a_verb(self):
        unit = self.unit('走っている', [self.word('走っている', 'はしっている')], 0, 3)
        self.assertEqual(unit['segments'], [('走って', 'はしって')])
        self.assertEqual(unit['reading'], 'はしって')

    def test_kana_part_stays_as_written(self):
        unit = self.unit('走っている', [self.word('走っている', 'はしっている')], 3, 5)
        self.assertEqual(unit['segments'], [('いる', 'いる')])

    def test_whole_word_is_unchanged(self):
        unit = self.unit('走って', [self.word('走って', 'はしって')], 0, 3)
        self.assertEqual(unit['segments'], [('走って', 'はしって')])

    def test_no_word_under_it(self):
        unit = self.unit('走って', [], 0, 2)
        self.assertEqual(unit['segments'], [('走っ', '')])


@unittest.skipUnless(__import__('morphology').HAS_JANOME, 'requires native Janome dictionary')
class Homophones(unittest.TestCase):
    def test_same_ending_as_the_range(self):
        from candidates import build_range_candidates
        from vocabulary import VocabularyStore, find_known_readings_flex

        class Index:
            def readings_for_surface(self, text): return []
            def surfaces_for_reading(self, reading): return {'とる': ['取る', '撮る', '捕る']}.get(reading, [])
        got = build_range_candidates([('取って', 'とって')], VocabularyStore(), find_known_readings_flex, dict_index=Index())
        surfaces = [c['surface'] for c in got if c['kind'] == 'homophone']
        self.assertIn('撮って', surfaces)
        self.assertIn('捕って', surfaces)
        self.assertNotIn('取って', surfaces)


if __name__ == '__main__':
    unittest.main()
