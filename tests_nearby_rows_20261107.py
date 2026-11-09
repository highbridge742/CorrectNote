# -*- coding: utf-8 -*-
"""Rows picked only because their nearby words changed are solved again only when correction_entry says the
change matters (batch279 marks, 2026-11-07). Anything not known is solved again."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app as A
import correction_entry


WORDS = {'上の行': ['上'], '下の行': ['下'], '新しい行': ['新'], '別の行': ['別'], 'もう一行': ['もう']}


def fake():
    me = SimpleNamespace(_deferred_neighbors=set(), _line_words_cache={})
    me._words_of_text = lambda line: WORDS.get(line, [])
    return me


def res(**uk):
    return dict(original='x', used_keys=dict(uk))


class Rows(unittest.TestCase):
    prev = ['上の行', '別の行', '下の行', 'もう一行']
    lines = ['上の行', '別の行', '新しい行', '下の行', 'もう一行']      # a row put in at index 2

    def pick(self, results, matters=lambda uk, a, b: False, me=None):
        me = me or fake()
        with patch.object(correction_entry, 'nearby_change_matters', matters):
            return A.CorrectNoteApp._nearby_rows_that_matter(me, [0, 1, 3, 4], self.prev, self.lines, 2, 2, results)

    def test_unread_nearby_is_kept(self):
        results = [res(nearby=False)] * 2 + [None] + [res(nearby=False)] * 2
        # row 3 is just below the change (its previous line changed): always again
        self.assertEqual(self.pick(results), [3])

    def test_the_function_decides(self):
        results = [res(nearby=True)] * 2 + [None] + [res(nearby=True)] * 2
        self.assertEqual(self.pick(results, matters=lambda uk, a, b: True), [0, 1, 3, 4])

    def test_it_gets_the_old_and_new_nearby_words(self):
        seen = []
        results = [res(nearby=False)] * 2 + [None] + [res(nearby=False)] * 2
        self.pick(results, matters=lambda uk, a, b: seen.append((tuple(a), tuple(b))) or False)
        self.assertEqual(seen[1], (('上', '下', 'もう'), ('上', '新', '下')))     # row 1: old rows 0,2,3 / new rows 0,2,3

    def test_unknown_is_solved_again(self):
        results = [dict(original='x'), dict(original='x', pending=True), None,
                   dict(original='x', deferred_stages=['x'], used_keys={}), None]
        self.assertEqual(self.pick(results), [0, 1, 3, 4])

    def test_waiting_rows_and_failures_are_solved_again(self):
        me = fake()
        me._deferred_neighbors = {(1, '別の行')}
        results = [res(nearby=False)] * 2 + [None] + [res(nearby=False)] * 2
        self.assertEqual(self.pick(results, me=me), [1, 3])

        def boom(uk, a, b):
            raise RuntimeError
        self.assertEqual(self.pick(results, matters=boom), [0, 1, 3, 4])


if __name__ == '__main__':
    unittest.main()
