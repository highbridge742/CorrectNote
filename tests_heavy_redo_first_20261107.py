# -*- coding: utf-8 -*-
"""The typed row's heavy redo goes to the front of the rows still to be read in this tab (2026-11-07, うにさんの優先順
「今打った分 → 見えている範囲 → 下の先読み → 次のタブ」). Before, it waited for every remaining row of the tab."""
from types import SimpleNamespace
import unittest

import app
import analysis_work_app as input_work


def make(todo, pos, pending_row=None, **extra):
    a = SimpleNamespace(_analyze_todo=list(todo), _analyze_pos=pos, _analyze_units_only=False,
                        _initial_setup=None, _after_id=None, _input_display_job=None, _async_context_scope=None,
                        _warmup=None, _tab_warming=False, _heavy_redo=set(),
                        _async_request=None if pending_row is None else (('line', 'w', 'd', 't', pending_row, False), 7))
    a.__dict__.update(extra)
    return a


class PutFirst(unittest.TestCase):
    def setUp(self):
        self.real = input_work.token
        input_work.token = lambda a: getattr(a, '_analyze_work', None)

    def tearDown(self):
        input_work.token = self.real

    def test_goes_next_after_the_row_being_computed(self):
        a = make([10, 11, 12, 5, 13], pos=1, pending_row=11, _analyze_work='w')
        self.assertTrue(app.CorrectNoteApp._put_heavy_redo_first(a, [5]))
        self.assertEqual(a._analyze_todo, [10, 11, 5, 12, 13])     # 11 is with the child; 5 next, once only
        self.assertEqual(a._analyze_pos, 1)
        self.assertEqual(a._heavy_redo, {5})

    def test_goes_first_when_nothing_is_asked(self):
        a = make([10, 11, 12], pos=1, _analyze_work='w')
        self.assertTrue(app.CorrectNoteApp._put_heavy_redo_first(a, [5]))
        self.assertEqual(a._analyze_todo, [10, 5, 11, 12])

    def test_other_preparation_still_waits(self):
        for extra in (dict(_async_context_scope=('prepare',)), dict(_after_id='job'), dict(_warmup=object()),
                      dict(_analyze_units_only=True), dict(_analyze_work='old')):
            a = make([10, 11], pos=0, **dict(dict(_analyze_work='w'), **extra))
            if extra.get('_analyze_work') == 'old':
                input_work.token = lambda a: 'new'
            self.assertFalse(app.CorrectNoteApp._put_heavy_redo_first(a, [5]), extra)
            self.assertEqual(a._analyze_todo, [10, 11])
            input_work.token = lambda a: getattr(a, '_analyze_work', None)

    def test_the_end_of_the_pass_is_not_touched(self):
        a = make([10, 11], pos=2, _analyze_work='w')
        self.assertFalse(app.CorrectNoteApp._put_heavy_redo_first(a, [5]))


class RedoNext(unittest.TestCase):
    def setUp(self):
        self.real = input_work.token
        input_work.token = lambda a: 'w'

    def tearDown(self):
        input_work.token = self.real

    def make(self, edited_ago, priority=('w', 5)):
        import time
        return SimpleNamespace(NEIGHBOR_DEFER_MS=1200, _last_edit_at=time.monotonic() - edited_ago,
                               _priority_input_row=priority, _analyze_todo=[3, 5, 8, 5, 9], _heavy_redo=set())

    def test_hands_still_the_typed_row_is_next(self):
        a = self.make(5.0)
        app.CorrectNoteApp._heavy_redo_next(a, 1, 5)
        self.assertEqual(a._analyze_todo, [3, 5, 5, 8, 9])
        self.assertEqual(a._heavy_redo, {5})

    def test_still_typing_or_not_the_typed_row(self):
        for a, pos, row in ((self.make(0.2), 1, 5), (self.make(5.0, priority=('w', 8)), 1, 5),
                            (self.make(5.0, priority=('old', 5)), 1, 5), (self.make(5.0), 2, 5)):
            app.CorrectNoteApp._heavy_redo_next(a, pos, row)
            self.assertEqual(a._analyze_todo, [3, 5, 8, 5, 9])


if __name__ == '__main__':
    unittest.main()
