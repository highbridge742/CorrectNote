# -*- coding: utf-8 -*-
"""The waits for the neighbour rows and the heavy redo count from the last keystroke (2026-11-07, speed).

Before, both re-armed 1.2 s from when they found another analysis running, so a typed row whose light answer
took 9 s waited up to 1.2 s more (0.8 s measured) before its neighbours and its heavy redo."""
import time
import unittest
from types import SimpleNamespace

import app as A


class Root:
    def __init__(self):
        self.calls = []

    def after(self, ms, fn):
        self.calls.append(ms)
        return 'job%d' % len(self.calls)

    def after_cancel(self, job):
        pass


def fake(pending=False, edited_ago=None, neighbor_job=None):
    me = SimpleNamespace(root=Root(), NEIGHBOR_DEFER_MS=A.CorrectNoteApp.NEIGHBOR_DEFER_MS, _heavy_redo_job=None,
                         _neighbor_defer_job=neighbor_job, _deferred_neighbors={(3, 'x')}, _closing=False, analyzed=[])
    if edited_ago is not None:
        me._last_edit_at = time.monotonic() - edited_ago
    me._foreground_analysis_pending = lambda: pending
    me._flush_heavy_redo = lambda: None
    me._flush_deferred_neighbors = lambda: A.CorrectNoteApp._flush_deferred_neighbors(me)
    me._heavy_redo_waiting = lambda: A.CorrectNoteApp._heavy_redo_waiting(me)
    me._analyze = lambda: me.analyzed.append(getattr(me, '_neighbor_force', None))
    return me


class HeavyRedo(unittest.TestCase):
    def arm(self, **kw):
        me = fake(**kw)
        A.CorrectNoteApp._arm_heavy_redo(me)
        return me.root.calls[-1]

    def test_counts_from_the_last_keystroke(self):
        self.assertEqual(self.arm(edited_ago=5.0), 20)            # hands long stopped: almost at once
        left = self.arm(edited_ago=0.3)
        self.assertTrue(850 <= left <= 900, left)                  # 1.2 s after the keystroke, not after now
        self.assertEqual(self.arm(edited_ago=0.0), 1200)

    def test_another_analysis_first_is_looked_at_often(self):
        self.assertEqual(self.arm(edited_ago=5.0, pending=True), 100)
        # the neighbours' redo waits for the typed row's heavy redo, not the other way round
        self.assertEqual(self.arm(edited_ago=5.0, neighbor_job='j'), 20)

    def test_without_typing_it_waits_as_before(self):
        self.assertEqual(self.arm(), 1200)                         # start, restored rows: no keystroke yet


class Neighbours(unittest.TestCase):
    def test_while_the_typed_row_is_solved_it_looks_every_tenth(self):
        me = fake(pending=True, edited_ago=5.0)
        A.CorrectNoteApp._flush_deferred_neighbors(me)
        self.assertEqual(me.root.calls, [100])
        self.assertEqual(me.analyzed, [])

    def test_hands_still_moving_it_waits_the_rest(self):
        me = fake(edited_ago=0.5)
        A.CorrectNoteApp._flush_deferred_neighbors(me)
        self.assertEqual(len(me.root.calls), 1)
        self.assertTrue(650 <= me.root.calls[0] <= 700, me.root.calls)
        self.assertEqual(me.analyzed, [])

    def test_hands_stopped_it_runs_now(self):
        me = fake(edited_ago=2.0)
        A.CorrectNoteApp._flush_deferred_neighbors(me)
        self.assertEqual(me.root.calls, [])
        self.assertEqual(me.analyzed, [True])

    def test_the_typed_rows_heavy_redo_goes_first(self):
        me = fake(edited_ago=5.0)
        me._heavy_redo_job = 'booked'
        A.CorrectNoteApp._flush_deferred_neighbors(me)
        self.assertEqual((me.root.calls, me.analyzed), ([100], []))

    def test_nothing_waiting_does_nothing(self):
        me = fake(edited_ago=2.0)
        me._deferred_neighbors = set()
        A.CorrectNoteApp._flush_deferred_neighbors(me)
        self.assertEqual((me.root.calls, me.analyzed), ([], []))


if __name__ == '__main__':
    unittest.main()
