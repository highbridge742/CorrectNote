# -*- coding: utf-8 -*-
"""The re-conversion candidates follow the input method (2026-10-26, wiring of candidates.build_candidates'
input_method): with kana input a 50-sound mix-up (カレー → カラー・クレー) is not offered as a typing slip, with
romaji input it still is. Every candidate call in app.py passes the setting (the memo pane, the corrected pane,
the quick window, the range re-conversion and the kana block's kanji)."""
import ast
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import candidates
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

HERE = os.path.dirname(os.path.abspath(__file__))


class CandidateInputMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        for surface, reading in (('カラー', 'からー'), ('クレー', 'くれー'), ('カレー', 'かれー')):
            cls.store.add(reading, surface, solid=True)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def surfaces(self, method):
        return [c['surface'] for c in candidates.build_candidates(
            'カレー', 'かれー', self.store, find_known_readings_flex, dict_index=self.index, input_method=method)]

    def test_kana_input_does_not_offer_the_50_sound_mix_up(self):
        got = self.surfaces('kana')
        self.assertNotIn('カラー', got)
        self.assertNotIn('クレー', got)

    def test_romaji_input_still_offers_them(self):
        got = self.surfaces('romaji')
        self.assertIn('カラー', got)
        self.assertIn('クレー', got)

    def test_range_candidates_follow_it_too(self):
        segments = [('カレー', 'かれー')]        # units.make_range_unit's (text, reading)
        got = {m: {c['surface'] for c in candidates.build_range_candidates(
            segments, self.store, find_known_readings_flex, dict_index=self.index, input_method=m)}
            for m in ('kana', 'romaji')}
        self.assertFalse({'カラー', 'クレー'} & got['kana'], got)
        self.assertEqual({'カラー', 'クレー'} & got['romaji'], {'カラー', 'クレー'}, got)


class AppWiringTests(unittest.TestCase):
    def test_every_candidate_call_in_app_passes_the_input_method(self):
        with open(os.path.join(HERE, 'app.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id in ('build_candidates', 'build_range_candidates')]
        self.assertGreaterEqual(len(calls), 7)
        missing = [n.lineno for n in calls if not any(k.arg == 'input_method' for k in n.keywords)]
        self.assertEqual(missing, [], 'app.py lines without input_method: %s' % missing)

    def test_the_setting_is_what_goes_in(self):
        import app
        seen = []

        def fake(*args, **kwargs):
            seen.append(kwargs.get('input_method'))
            return []
        for method in ('kana', 'romaji'):
            owner = SimpleNamespace(settings={'input_method': method}, store=self.__class__, dict_index=None,
                                    context_vec=None, _attested_surfaces=None)
            with patch.object(app, 'build_candidates', fake):
                app.CorrectNoteApp._functional_kanji_cands(
                    owner, {'base': 'かれーです', 'reading': 'かれーです', 'text': 'かれーです'}, ())
        self.assertEqual(seen, ['kana', 'romaji'])


if __name__ == '__main__':
    unittest.main()
