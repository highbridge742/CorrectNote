# -*- coding: utf-8 -*-
"""同音の語の選び直しで解き直すのは、その前後の並びが現れる行だけ（作った例・2026-11-03）。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import analysis_worker as W
import used_changes as U
from last_choice import LastChoiceStore

U.install()


def store():
    s = LastChoiceStore()
    s._is_homophone_swap = lambda original, chosen, reading: reading == 'homo'
    return s


class Keys(unittest.TestCase):
    def test_homophone_swap_notes_the_context_only(self):
        s = store()
        before = s._revision
        s.record('買える', '変える', 'homo', 'よって', 'ので')
        keys = U.changed(s, before, s._revision)
        places, rest = U.split_context_keys(keys)
        self.assertEqual(places, ['よって買えるので'])
        self.assertEqual(rest, frozenset())

    def test_other_choice_notes_the_words(self):
        s = store()
        before = s._revision
        s.record('かう', '買う', 'かう')
        places, rest = U.split_context_keys(U.changed(s, before, s._revision))
        self.assertEqual(places, [])
        self.assertIn('かう', rest)

    def test_answer_of_lookup_is_the_same(self):
        s = store()
        s.record('買える', '変える', 'homo', 'よって', 'ので')
        self.assertEqual(s.lookup('買える', 'よって', 'ので'), '変える')
        self.assertIsNone(s.lookup('買える', '金で', ''))


class Rows(unittest.TestCase):
    def state(self, choice):
        previous = [None] * 10
        previous[W.CHOICE] = choice
        previous[W.VOCAB] = 0
        previous[W.RECENT] = ()
        return tuple(previous)

    def unchanged(self, app, row, old, new):
        with patch.object(W, '_choice_part', lambda v: v), patch.object(W, '_decision_part', lambda v: 0):
            return W._keys_unchanged(app, row, self.state(old), self.state(new))

    def test_only_the_row_with_the_context_is_redone(self):
        s = store()
        old = s._revision
        s.record('買える', '変える', 'homo', 'よって', 'ので')
        app = NS(choices=s, store=None)
        used = dict(choice=['買える', 'かえる'], vocab=[])
        here = dict(original='モードによって買えるので直す', corrected='モードによって買えるので直す', used_keys=used)
        other = dict(original='金で買える物です', corrected='金で買える物です', used_keys=used)
        self.assertFalse(self.unchanged(app, here, old, s._revision))
        self.assertTrue(self.unchanged(app, other, old, s._revision))

    def test_a_row_that_became_the_context_by_a_fix_is_redone(self):
        s = store()
        old = s._revision
        s.record('買える', '変える', 'homo', 'よって', '')
        row = dict(original='よって飼える', corrected='よって買える', used_keys=dict(choice=[], vocab=[]))
        self.assertFalse(self.unchanged(NS(choices=s, store=None), row, old, s._revision))

    def test_other_choice_still_by_keys(self):
        s = store()
        old = s._revision
        s.record('かう', '買う', 'かう')
        app = NS(choices=s, store=None)
        self.assertFalse(self.unchanged(app, dict(original='x', corrected='x', used_keys=dict(choice=['かう'], vocab=[])), old, s._revision))
        self.assertTrue(self.unchanged(app, dict(original='x', corrected='x', used_keys=dict(choice=['ほか'], vocab=[])), old, s._revision))


if __name__ == '__main__':
    unittest.main()
