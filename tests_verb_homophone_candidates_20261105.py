# -*- coding: utf-8 -*-
"""2026-11-05 うに「つかれているを突かれているに変換したかったが、候補に出なかった」:
活用した動詞の同じ読みの別の語も「漢字にする」候補に出す（読みの表の4つに埋もれない）。"""
import unittest

from candidates import build_candidates


class _Store:
    def lookup(self, reading):
        return []


def kanji(surface):
    found = lambda *a, **k: []
    return [c['surface'] for c in build_candidates(surface, surface, _Store(), found) if c['kind'] == 'kanji']


class VerbHomophoneTests(unittest.TestCase):
    def test_other_verbs_of_the_same_reading(self):
        self.assertIn('突かれ', kanji('つかれ'))
        self.assertIn('撮られ', kanji('とられ'))
        self.assertIn('切られ', kanji('きられ'))

    def test_existing_first(self):
        got = kanji('つかれ')
        self.assertLess(got.index('疲れ'), got.index('突かれ'))


if __name__ == '__main__':
    unittest.main()
