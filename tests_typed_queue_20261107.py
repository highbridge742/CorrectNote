# -*- coding: utf-8 -*-
"""Typed rows in typed order (2026-11-07 うにさん「最優先はその前に入力した文。今の行はその後」): the plan puts the typed
rows first in the order they were typed (the row typed now last), a typed row waiting for its heavy redo keeps its place;
other rows wait while the queue has work, while converting, and for NEIGHBOR_DEFER_MS after the queue was busy or the
last key; a typed row being computed in the child is waited for unless that row itself was typed again."""
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app
import analysis_async
import analysis_work_app as input_work


def row(text, **extra):
    return dict(original=text, corrected=text, **extra)


class TypedRowsFirst(unittest.TestCase):
    def setUp(self):
        self.real = input_work.token
        input_work.token = lambda a: 'w'

    def tearDown(self):
        input_work.token = self.real

    def make(self, order, results, priority):
        return SimpleNamespace(_typed_order=list(order), line_results=results, _priority_input_row=('w', priority),
                               _heavy_redo=set(), _plan_changed=(priority, priority + 1))

    def test_typed_order_then_the_rest(self):
        results = [row('a'), row('b', pending=True), row('c'), row('d', pending=True), row('e', pending=True)]
        a = self.make([3], results, priority=1)
        todo, first = app.CorrectNoteApp._typed_rows_first(a, [1, 3, 4], True)
        self.assertEqual(todo, [3, 1, 4])           # 3 was typed before 1
        self.assertTrue(first)
        self.assertEqual(a._typed_order, [3, 1])

    def test_a_plan_without_an_edit_of_the_row_adds_nothing(self):
        # after learning: the last typed row is solved again, but it was not typed now (the background's turn)
        results = [row('a', pending=True), row('b', pending=True)]
        a = self.make([], results, priority=0); a._plan_changed = None
        todo, first = app.CorrectNoteApp._typed_rows_first(a, [0, 1], True)
        self.assertEqual(a._typed_order, [])
        self.assertEqual(todo, [0, 1])

    def test_waiting_heavy_redo_keeps_its_place_and_finished_rows_leave(self):
        results = [row('a', deferred_stages=['x']), row('b'), row('c', pending=True)]
        a = self.make([0, 1], results, priority=2)
        todo, first = app.CorrectNoteApp._typed_rows_first(a, [2], True)
        self.assertEqual(todo, [0, 2])              # 0's heavy redo before the row typed now; 1 is done
        self.assertEqual(a._typed_order, [0, 2])
        self.assertIn(0, a._heavy_redo)


class BackgroundWaits(unittest.TestCase):
    def make(self, order, results, edited_ago=10.0, busy_ago=None):
        now = time.monotonic()
        return SimpleNamespace(TYPED_QUEUE=True, NEIGHBOR_DEFER_MS=1200, _typed_order=order, line_results=results,
                               _last_edit_at=now - edited_ago,
                               _typed_queue_busy_at=None if busy_ago is None else now - busy_ago,
                               editor=SimpleNamespace(winfo_id=lambda: 1))

    def test_rules(self):
        done = [row('a'), row('b')]
        with patch('ime_watch.composition_live', return_value=False):
            self.assertFalse(analysis_async.background_waits(self.make([0], done), 1))
            self.assertTrue(analysis_async.background_waits(self.make([0], [row('a', pending=True), row('b')]), 1))
            self.assertTrue(analysis_async.background_waits(self.make([0], [row('a', deferred_stages=['x']), row('b')]), 1))
            self.assertFalse(analysis_async.background_waits(self.make([0], [row('a', pending=True), row('b')]), 0))  # typed itself
            self.assertTrue(analysis_async.background_waits(self.make([0], done, edited_ago=0.5), 1))
            self.assertTrue(analysis_async.background_waits(self.make([0], done, busy_ago=0.5), 1))
            self.assertFalse(analysis_async.background_waits(self.make([0], done, busy_ago=1.5), 1))
        with patch('ime_watch.composition_live', return_value=True):
            self.assertTrue(analysis_async.background_waits(self.make([0], done), 1))


class FinishTypedInflight(unittest.TestCase):
    def make(self, typed_row, now_text):
        prev = ['one', 'two', 'three']
        scope = ('line', 'w', 'd', '\n'.join(prev), typed_row, False)
        return SimpleNamespace(TYPED_QUEUE=True, _async_request=(scope, 4), _typed_order=[typed_row], _analyze_work='w',
                               _analyze_text='\n'.join(prev), _prev_lines=prev, editor_source_text=lambda: now_text)

    def test_waits_for_the_typed_row_unless_it_was_typed_again(self):
        with patch.object(analysis_async, '_poll', return_value=(True, None)):
            self.assertEqual(analysis_async.finish_typed_inflight(self.make(0, 'one\ntwo\nthree\nfour')), 'wait')
            self.assertIsNone(analysis_async.finish_typed_inflight(self.make(0, 'onee\ntwo\nthree')))
            a = self.make(0, 'one\ntwo\nthree\nfour'); a._typed_order = []
            self.assertIsNone(analysis_async.finish_typed_inflight(a))       # not a typed row: the new plan supersedes it


if __name__ == '__main__':
    unittest.main()
