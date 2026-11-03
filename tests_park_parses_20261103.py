# -*- coding: utf-8 -*-
"""A tab left behind keeps its parsed rows, packed, for when it comes back (2026-11-03)."""
import unittest
from types import SimpleNamespace
from unittest import mock

import analysis_async
from analysis_worker import Runtime


def _runtime(lines):
    run = Runtime.__new__(Runtime)
    run.line_tokens = {line: [('rows', line)] for line in lines}
    run.content_words = {line: ['word', line] for line in lines}
    run._parked = []
    return run


class Park(unittest.TestCase):
    LINES = ['row %d' % i for i in range(Runtime.PARK_MIN_LINES)]

    def test_back_with_the_same_rows(self):
        run = _runtime(self.LINES)
        run._park_parses()
        run.line_tokens, run.content_words = {}, {}
        run._take_parked(frozenset(self.LINES))
        self.assertEqual(run.line_tokens, {line: [('rows', line)] for line in self.LINES})
        self.assertEqual(run.content_words, {line: ['word', line] for line in self.LINES})
        self.assertEqual(run._parked, [])

    def test_only_the_rows_of_the_tab_now(self):
        run = _runtime(self.LINES)
        run._park_parses()
        run.line_tokens, run.content_words = {}, {}
        changed = frozenset(self.LINES[1:] + ['new'])
        run._take_parked(changed)
        self.assertNotIn(self.LINES[0], run.line_tokens)
        self.assertNotIn('new', run.line_tokens)

    def test_another_tab_takes_nothing(self):
        run = _runtime(self.LINES)
        run._park_parses()
        run.line_tokens, run.content_words = {}, {}
        run._take_parked(frozenset(['something else']))
        self.assertEqual(run.line_tokens, {})
        self.assertEqual(len(run._parked), 1)

    def test_a_row_the_fallback_split_is_not_kept(self):
        run = _runtime(self.LINES)
        run.content_words['fallback row'] = ['word']
        run._park_parses()
        run.line_tokens, run.content_words = {}, {}
        run._take_parked(frozenset(self.LINES + ['fallback row']))
        self.assertNotIn('fallback row', run.content_words)

    def test_a_short_tab_is_not_packed_and_two_at_most(self):
        run = _runtime(self.LINES[:5])
        run._park_parses()
        self.assertEqual(run._parked, [])
        for n in range(3):
            run.line_tokens = {'%d %s' % (n, line): [] for line in self.LINES}
            run.content_words = {}
            run._park_parses()
        self.assertEqual(len(run._parked), Runtime.PARK_TABS)


class KeptByTheWindow(unittest.TestCase):
    class Worker:
        def __init__(self, answer):
            self.answer = answer
            self.process = SimpleNamespace(is_alive=lambda: True)
            self.asked = []
        def submit(self, task):
            self.asked.append(task)
            return 1
        def poll(self, identifier):
            return self.answer

    def test_kept_sent_with_the_prepare_and_dropped_when_answered(self):
        app = SimpleNamespace()
        worker = self.Worker(dict(tabs=[(frozenset(['a', 'b']), b'rows')]))
        analysis_async.keep_rows(app, worker)
        self.assertEqual(worker.asked, [dict(kind='packed_rows')])
        self.assertEqual(analysis_async._packed_for(app, ['a', 'b', 'c']), b'rows')
        self.assertIsNone(analysis_async._packed_for(app, ['x', 'y']))
        analysis_async._drop_packed(app, ['a', 'b'])
        self.assertIsNone(analysis_async._packed_for(app, ['a', 'b']))

    def test_a_silent_child_keeps_nothing(self):
        app = SimpleNamespace()
        with mock.patch.object(analysis_async, 'PACKED_ROWS_WAIT_S', 0.0):
            analysis_async.keep_rows(app, self.Worker(None))
        self.assertIsNone(analysis_async._packed_for(app, ['a']))

    def test_a_short_tab_keeps_nothing(self):
        app = SimpleNamespace()
        analysis_async.keep_rows(app, self.Worker(dict(tabs=[])))
        self.assertIsNone(analysis_async._packed_for(app, ['a']))

    def test_the_child_gives_the_tab_left_behind_too(self):
        lines = ['row %d' % i for i in range(Runtime.PARK_MIN_LINES)]
        run = _runtime(lines)
        run._park_parses()
        run.line_tokens, run.content_words = {'small': []}, {}
        got = Runtime.execute(run, dict(kind='packed_rows'))
        self.assertEqual([tab[0] for tab in got['tabs']], [frozenset(lines)])

    def test_the_next_child_unpacks_them(self):
        lines = ['row %d' % i for i in range(Runtime.PARK_MIN_LINES)]
        giver = _runtime(lines)
        taker = _runtime([])
        taker._unpack_rows(giver._pack_rows(), frozenset(lines))
        self.assertEqual(taker.line_tokens, giver.line_tokens)
        self.assertEqual(taker.content_words, {line: giver.content_words[line] for line in lines})


if __name__ == '__main__':
    unittest.main()
