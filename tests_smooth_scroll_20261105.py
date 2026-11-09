# -*- coding: utf-8 -*-
"""Scrolling: the marks are measured again less often while the view is moving (2026-11-05 「処理落ちしたように」)."""
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app as app_module

App = app_module.CorrectNoteApp


class Fake:
    _after_view_moved = App._after_view_moved
    _scrolling_now = App._scrolling_now
    VIEW_PAINT_WHILE_SCROLLING_S = App.VIEW_PAINT_WHILE_SCROLLING_S
    WS_SCROLL_SETTLE_MS = App.WS_SCROLL_SETTLE_MS

    def __init__(self):
        self.painted = 0
        self.root = mock.Mock()
        self.root.after = mock.Mock(return_value='job')
        self._view_moved_job = None
        self._scroll_inertia = NS(job=None)
        self._drag = None

    def _window_dragging(self):
        return False

    def _schedule_whitespace_paint(self, delay=None):
        self.painted += 1


class Thinning(unittest.TestCase):
    def run_once(self, a):
        try:
            a._after_view_moved()
        except AttributeError:
            pass        # past the part this test is about

    def test_at_rest_it_paints_at_once(self):
        a = Fake()
        self.run_once(a)
        self.assertEqual(a.painted, 1)

    def test_while_the_wheel_moves_it_waits_its_turn(self):
        a = Fake()
        a._scroll_inertia.job = 'tick'
        with mock.patch('time.monotonic', return_value=100.0):
            self.run_once(a)
            self.assertEqual(a.painted, 1)
            a._view_moved_job = None
            self.run_once(a)
        self.assertEqual(a.painted, 1)
        self.assertEqual(a._view_moved_job, 'job')
        with mock.patch('time.monotonic', return_value=100.0 + a.VIEW_PAINT_WHILE_SCROLLING_S + .01):
            self.run_once(a)
        self.assertEqual(a.painted, 2)

    def test_a_right_drag_counts_as_moving(self):
        a = Fake()
        a._drag = dict(mode='scroll')
        self.assertTrue(a._scrolling_now())
        a._drag = dict(mode='select')
        self.assertFalse(a._scrolling_now())

    def test_when_it_stops_it_paints_at_once(self):
        a = Fake()
        a._scroll_inertia.job = 'tick'
        with mock.patch('time.monotonic', return_value=100.0):
            self.run_once(a)
            a._scroll_inertia.job = None
            self.run_once(a)
        self.assertEqual(a.painted, 2)


if __name__ == '__main__':
    unittest.main()
