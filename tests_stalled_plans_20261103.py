# -*- coding: utf-8 -*-
"""A finished row without a plan must get one: nothing else brings it, and the row stayed marked as unanalysed."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_async
import boundary_colors
from boundary_colors import BoundaryColors


class Pane:
    def __init__(self, text):
        self.text = text

    def get(self, start, end):
        return self.text


def colors_for(results, widget_is_editor=True):
    c = BoundaryColors.__new__(BoundaryColors)
    pane = Pane('文')
    app = SimpleNamespace(line_results=results, editor=pane if widget_is_editor else object(), result_view=pane if not widget_is_editor else object(), _ctrl_boundary_plans={})
    c.app = app
    c.widget = pane
    c._plans_failed = set()
    c._plans_scope = None
    c._plans_job = None
    c._closed = False
    c._painted = {}
    c._last_plans = {}
    return c


class FinishedRow(unittest.TestCase):
    def test_memo_row_finished_is_asked_for(self):
        c = colors_for([dict(original='文', corrected='文')])
        self.assertTrue(c._finished_row(c.widget, 1, '文'))

    def test_memo_row_pending_waits_for_its_analysis(self):
        c = colors_for([dict(original='文', corrected='文', pending=True)])
        self.assertFalse(c._finished_row(c.widget, 1, '文'))

    def test_memo_row_with_other_text_waits(self):
        # An edit moved the rows: this result is not this row's
        c = colors_for([dict(original='別', corrected='別')])
        self.assertFalse(c._finished_row(c.widget, 1, '文'))

    def test_no_result(self):
        c = colors_for([])
        self.assertFalse(c._finished_row(c.widget, 1, '文'))

    def test_given_up_row_is_made_here(self):
        c = colors_for([dict(original='文', corrected='文')])
        c._plans_failed.add('文')
        with patch.object(analysis_async, 'child_alive', return_value=True), \
                patch.object(BoundaryColors, '_plan_now', return_value='plan') as made, \
                patch.object(BoundaryColors, '_ask_plans_soon') as asked:
            self.assertEqual(c._plan_missing(1, '文'), 'plan')
        made.assert_called_once_with('文')
        asked.assert_not_called()

    def test_not_given_up_asks_the_child(self):
        c = colors_for([dict(original='文', corrected='文')])
        with patch.object(analysis_async, 'child_alive', return_value=True), \
                patch.object(BoundaryColors, '_plan_now') as made, \
                patch.object(BoundaryColors, '_ask_plans_soon') as asked:
            self.assertIsNone(c._plan_missing(1, '文'))
        made.assert_not_called()
        asked.assert_called_once_with('文')


class HelperDone(unittest.TestCase):
    def app(self, results, done=(), row=None):
        a = SimpleNamespace(line_results=results, _analyze_work=1, _analyze_dependencies=2, _analyze_text='t')
        a._helper = dict(key=analysis_async._helper_key(a), done=set(done), row=row)
        return a

    def test_finished_row_is_passed_over(self):
        a = self.app([dict(original='文', corrected='文')], done=(0,))
        self.assertTrue(analysis_async.helper_done(a, 0))

    def test_row_pending_again_is_not_passed_over(self):
        a = self.app([dict(original='文', corrected='文', pending=True)], done=(0,))
        self.assertFalse(analysis_async.helper_done(a, 0))

    def test_row_with_the_helper_is_passed_over(self):
        a = self.app([dict(original='文', corrected='文', pending=True)], row=0)
        self.assertTrue(analysis_async.helper_done(a, 0))


if __name__ == '__main__':
    unittest.main()
