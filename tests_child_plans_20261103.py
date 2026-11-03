# -*- coding: utf-8 -*-
"""Rows on screen with no plan: the child makes them, the window's own tables stay unread (2026-11-03)."""
import unittest
from types import SimpleNamespace
from unittest import mock

import analysis_async
import boundary_colors
from text_navigation import plans


class _Widget:
    def __init__(self):
        self.later = []
    def after(self, ms, fn):
        self.later.append((ms, fn))
        return len(self.later)
    def after_cancel(self, job):
        pass


def _colors(app, rows):
    c = boundary_colors.BoundaryColors.__new__(boundary_colors.BoundaryColors)
    c.app = app
    c.widget = _Widget()
    c.widget.index = lambda at: '%d.0' % len(rows)
    c.widget.get = lambda a, b: rows[int(a.split('.')[0]) - 1]
    c._closed = False
    c._plans_job = None
    c._plans_failed = set()
    c._plans_scope = None
    c._plans_texts = ()
    c._plans_until = 0.0
    c._painted = {}
    c._last_plans = {}
    c.enabled = lambda: True
    c._composing = lambda: False
    c._visible_range = lambda: (1, len(rows))
    return c


class MissingPlan(unittest.TestCase):
    def test_with_a_child_the_window_does_not_tokenize(self):
        c = _colors(SimpleNamespace(line_results=[{'pending': False}]), ['文'])
        c._plan_now = mock.Mock()
        with mock.patch.object(analysis_async, 'child_alive', return_value=True):
            self.assertIsNone(c._plan_missing(1, '文'))
        c._plan_now.assert_not_called()
        self.assertEqual(len(c.widget.later), 1)

    def test_a_row_waiting_for_its_analysis_waits(self):
        c = _colors(SimpleNamespace(line_results=[{'pending': True}]), ['文'])
        c._plan_now = mock.Mock()
        with mock.patch.object(analysis_async, 'child_alive', return_value=False):
            self.assertIsNone(c._plan_missing(1, '文'))
        c._plan_now.assert_not_called()

    def test_no_child_and_a_finished_row_is_worked_out_here(self):
        c = _colors(SimpleNamespace(line_results=[{'pending': False}]), ['文'])
        c._plan_now = mock.Mock(return_value='plan')
        with mock.patch.object(analysis_async, 'child_alive', return_value=False):
            self.assertEqual(c._plan_missing(1, '文'), 'plan')


class Asking(unittest.TestCase):
    def app(self):
        return SimpleNamespace(_ctrl_boundary_plans={}, _last_edit_at=0.0, _async_request=None)

    def test_the_answer_is_remembered_without_waiting_for_it(self):
        app = self.app()
        c = _colors(app, ['文', ''])
        c._paint_visible_now = mock.Mock()
        with mock.patch.object(analysis_async, 'plans_ask', return_value=('plans', 1)) as ask:
            c._ask_plans()
        self.assertEqual(ask.call_args[0][1], ['文'])
        self.assertEqual(len(c.widget.later), 1)        # came back at once, a timer looks for the answer
        c._plans_until = float('inf')
        with mock.patch.object(analysis_async, 'plans_poll', return_value=(True, None)):
            c._poll_plans()
        self.assertEqual(len(c.widget.later), 2)
        with mock.patch.object(analysis_async, 'plans_poll', return_value=(True, {'文': (1,)})), \
                mock.patch.object(boundary_colors, 'remember') as remember:
            c._poll_plans()
        remember.assert_called_once_with(app, {'文': (1,)})
        self.assertIsNone(c._plans_scope)

    def test_a_silent_child_leaves_the_row_to_its_analysis(self):
        app = self.app()
        c = _colors(app, ['文'])
        with mock.patch.object(analysis_async, 'plans_ask', return_value=('plans', 1)):
            c._ask_plans()
        c._plans_until = 0.0
        with mock.patch.object(analysis_async, 'plans_poll', return_value=(True, None)), \
                mock.patch.object(analysis_async, 'plans_cancel') as cancel:
            c._poll_plans()
        cancel.assert_called_once()
        self.assertIn('文', c._plans_failed)
        with mock.patch.object(analysis_async, 'plans_ask') as ask:
            c._ask_plans()
        ask.assert_not_called()

    def test_typing_is_not_interrupted(self):
        import time
        app = self.app()
        app._last_edit_at = time.monotonic()
        c = _colors(app, ['文'])
        with mock.patch.object(analysis_async, 'plans_ask') as ask:
            c._ask_plans()
        ask.assert_not_called()
        self.assertEqual(len(c.widget.later), 1)

    def test_a_preparation_is_left_alone(self):
        app = self.app()
        app._async_request = (('prepare', 'work'), 1)
        c = _colors(app, ['文'])
        with mock.patch.object(analysis_async, 'plans_ask') as ask:
            c._ask_plans()
        ask.assert_not_called()
        self.assertEqual(len(c.widget.later), 1)


class LightAsk(unittest.TestCase):
    def test_no_child_is_started(self):
        app = SimpleNamespace(_correction_worker=None, _async_request=None)
        with mock.patch.object(analysis_async, '_request') as request:
            self.assertIsNone(analysis_async.plans_ask(app, ['文']))
        request.assert_not_called()

    def test_the_analysis_waits_for_the_answer(self):
        app = SimpleNamespace(_async_request=(('plans', 1), 7))
        self.assertTrue(analysis_async.plans_waiting(app))
        self.assertIsNone(analysis_async.line_step(app, 1))


class WorkerKind(unittest.TestCase):
    def test_the_same_function(self):
        import analysis_worker
        tokenize = lambda text: []
        run = SimpleNamespace(tokenize=tokenize)
        got = analysis_worker.Runtime.execute(run, dict(kind='plans', texts=['文']))
        self.assertEqual(got, plans(['文'], tokenize))


if __name__ == '__main__':
    unittest.main()
