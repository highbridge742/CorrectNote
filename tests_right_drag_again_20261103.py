# -*- coding: utf-8 -*-
"""Right-drag again and again: the press after a scroll is not a double press, and nothing goes back to the row the press saw (2026-11-03)."""
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app as app_module

App = app_module.CorrectNoteApp


class Double(unittest.TestCase):
    def press(self, a, widget, at):
        return App._right_press_is_double(a, NS(time=at, x_root=100, y_root=100), widget)

    def test_a_press_after_a_scroll_is_not_the_second_of_a_double(self):
        a = mock.MagicMock()
        widget = object()
        a._r3_last = None
        a.RIGHT_DOUBLE_MS = 500; a.RIGHT_DOUBLE_PX = 5
        self.assertFalse(self.press(a, widget, 1000))
        a._drag = dict(widget=widget, mode='scroll')
        a._overview = None
        a.settings.get.return_value = False
        App._drag_release(a, NS(num=3), widget)
        self.assertFalse(self.press(a, widget, 1200))

    def test_two_presses_without_a_scroll_still_are(self):
        a = mock.MagicMock()
        widget = object()
        a._r3_last = None
        a.RIGHT_DOUBLE_MS = 500; a.RIGHT_DOUBLE_PX = 5
        self.assertFalse(self.press(a, widget, 1000))
        a._drag = dict(widget=widget, mode=None)
        a._overview = None
        a._tab_wheel_used = False
        App._drag_release(a, NS(num=3), widget)
        self.assertTrue(self.press(a, widget, 1200))


class TkDouble(unittest.TestCase):
    def app(self):
        a = mock.MagicMock()
        a.RIGHT_AFTER_SCROLL_S = App.RIGHT_AFTER_SCROLL_S
        return a

    def test_tk_double_right_after_a_scroll_is_an_ordinary_press(self):
        a = self.app()
        a._r3_scrolled_at = app_module.time.monotonic()
        widget = object()
        event = NS(x_root=5, y_root=6)
        App._on_right_double(a, event, widget)
        a._overview_enter.assert_not_called()
        a._drag_press.assert_called_once_with(event, widget, True)
        self.assertEqual(a._r3_press, (5, 6))

    def test_tk_double_without_a_scroll_enters_the_overview(self):
        a = self.app()
        a._r3_scrolled_at = None
        App._on_right_double(a, NS(), object())
        a._overview_enter.assert_called_once()

    def test_a_scroll_long_ago_does_not_count(self):
        a = self.app()
        a._r3_scrolled_at = app_module.time.monotonic() - 5
        App._on_right_double(a, NS(), object())
        a._overview_enter.assert_called_once()

    def test_the_mark_is_used_once(self):
        a = self.app()
        a._r3_scrolled_at = app_module.time.monotonic()
        App._on_right_double(a, NS(x_root=1, y_root=1), object())
        self.assertIsNone(a._r3_scrolled_at)


class MinimumShow(unittest.TestCase):
    def app(self, shown_ago, moved=0, count=0):
        a = mock.MagicMock()
        a.OVERVIEW_MIN_SHOW_S = App.OVERVIEW_MIN_SHOW_S
        a._overview = dict(shown_at=app_module.time.monotonic() - shown_ago, moved=moved)
        a._view_moved_count = count
        a.root.after.return_value = 'job'
        return a

    def test_a_quick_release_keeps_it_on_screen(self):
        a = self.app(0.05)
        App._overview_exit_soon(a)
        a._overview_exit.assert_not_called()
        delay, callback = a.root.after.call_args[0]
        self.assertTrue(250 <= delay <= 300)
        self.assertIs(callback, a._overview_exit)
        self.assertEqual(a._overview_exit_job, 'job')

    def test_held_long_enough_goes_at_once(self):
        a = self.app(1.0)
        App._overview_exit_soon(a)
        a._overview_exit.assert_called_once()
        a.root.after.assert_not_called()

    def test_a_dragged_overview_goes_at_once(self):
        a = self.app(0.05, moved=1, count=2)
        App._overview_exit_soon(a)
        a._overview_exit.assert_called_once()

    def test_not_shown_yet_counts_from_when_it_is(self):
        a = self.app(0)
        a._overview['shown_at'] = float('inf')
        App._overview_exit_soon(a)
        self.assertGreater(a.root.after.call_args[0][0], 0)

    def test_a_press_while_waiting_goes_back_first(self):
        a = mock.MagicMock()
        a._overview_exit_job = 'job'
        try:
            App._drag_press(a, NS(x=0, y=0, x_root=0, y_root=0), object(), True)
        except Exception:
            pass
        a._overview_exit.assert_called_once()

    def test_a_double_while_waiting_comes_in_again(self):
        a = mock.MagicMock()
        a._overview = dict()
        a._overview_exit_job = 'job'
        def gone():
            a._overview = None
        a._overview_exit.side_effect = gone
        try:
            App._overview_enter(a, NS(x=0, y=0), mock.MagicMock())
        except Exception:
            pass
        a._overview_exit.assert_called_once()
        self.assertIsNotNone(a._overview)

    def test_the_exit_cancels_the_wait(self):
        a = mock.MagicMock()
        a._overview = None
        a._overview_exit_job = 'job'
        a._overview_cancel_exit = lambda: App._overview_cancel_exit(a)
        App._overview_exit(a)
        a.root.after_cancel.assert_called_once_with('job')
        self.assertIsNone(a._overview_exit_job)


class HandMoved(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root)
        a = self.a = App.__new__(App)
        a.root = self.root
        a.editor = self.text
        self.doubles = []
        a._on_right_double = lambda e, w: self.doubles.append(w)
        a._close_dropdown = lambda *x, **k: None
        a._drag_press = lambda *x, **k: None
        self.saved = app_module._input_message_time
        app_module._input_message_time = lambda: None

    def tearDown(self):
        app_module._input_message_time = self.saved
        self.root.destroy()

    def press(self, t, dx=0, dy=0):
        self.a._on_editor_right_press(NS(time=t, x=50 + dx, y=50 + dy, x_root=150 + dx, y_root=150 + dy, num=3))

    def test_a_little_movement_between_the_presses_is_still_a_double(self):
        for moved in (3, 8, 15):
            for dx, dy in ((moved, 0), (0, moved), (-moved, moved)):
                del self.doubles[:]
                self.a._r3_last = None
                self.press(1000)
                self.press(1150, dx, dy)
                self.assertEqual(self.doubles, [self.text], (dx, dy))

    def test_far_away_is_not(self):
        self.a._r3_last = None
        self.press(1000)
        self.press(1150, 60, 0)
        self.assertEqual(self.doubles, [])

    def test_a_scroll_that_did_not_move_the_view_keeps_the_double(self):
        self.a._r3_last = None
        self.press(1000)
        self.a._overview = None
        self.a._scroll_inertia = None
        self.a._restore_pointer = lambda d: None
        self.a._drag = dict(widget=self.text, mode='scroll', view_count=0)
        self.a._view_moved_count = 0
        self.a._drag_release(NS(num=3), self.text)
        self.assertIsNone(getattr(self.a, '_r3_scrolled_at', None))
        self.press(1150, 4, 4)
        self.assertEqual(self.doubles, [self.text])

    def test_a_scroll_that_moved_the_view_is_not_the_first_press(self):
        self.a._r3_last = None
        self.press(1000)
        self.a._overview = None
        self.a._scroll_inertia = None
        self.a._restore_pointer = lambda d: None
        self.a._drag = dict(widget=self.text, mode='scroll', view_count=0)
        self.a._view_moved_count = 1
        self.a._drag_release(NS(num=3), self.text)
        self.assertIsNotNone(self.a._r3_scrolled_at)
        self.press(1150)
        self.assertEqual(self.doubles, [])


class StillInOverview(unittest.TestCase):
    def motion(self, y, d):
        a = mock.MagicMock()
        a.OVERVIEW_STILL_PX = App.OVERVIEW_STILL_PX
        a.DRAG_WARP_TOLERANCE = App.DRAG_WARP_TOLERANCE
        a._drag = d
        a._overview = None
        a._get_line_height.return_value = 10
        widget = mock.MagicMock()
        d['widget'] = widget
        widget.winfo_pointery.return_value = y
        widget.winfo_rooty.return_value = 0
        App._drag_motion(a, NS(x=0, y=y), widget)
        return a

    def drag(self):
        return dict(mode='scroll', always_scroll=True, start_x=0, start_y=100, last_y=100, accum=0.0, still=True, press_root=None, warped=False)

    def test_a_shake_does_not_scroll(self):
        d = self.drag()
        a = self.motion(107, d)
        a._on_wheel_units.assert_not_called()
        self.assertTrue(d['still'])

    def test_a_real_move_scrolls_from_there(self):
        d = self.drag()
        a = self.motion(140, d)
        self.assertFalse(d['still'])
        a._on_wheel_units.assert_called()


class Settle(unittest.TestCase):
    def make(self):
        a = mock.MagicMock()
        a._layout_is_unified.return_value = True
        a.editor.yview.return_value = (0.0, 0.5)
        a.result_view.yview.return_value = (0.0, 0.5)
        return a

    def test_no_move_since_the_fonts_changed_puts_the_row_back(self):
        a = self.make(); a._view_moved_count = 3
        App._overview_settle(a, 40, False, 3)
        a.editor.yview.assert_any_call('40.0')

    def test_a_drag_since_then_is_left_alone(self):
        a = self.make(); a._view_moved_count = 4
        App._overview_settle(a, 40, False, 3)
        self.assertNotIn(mock.call('40.0'), a.editor.yview.call_args_list)

    def test_an_old_caller_without_the_count(self):
        a = self.make(); a._view_moved_count = 4
        App._overview_settle(a, 40, False)
        a.editor.yview.assert_any_call('40.0')

    def test_no_row(self):
        a = self.make(); a._view_moved_count = 4
        App._overview_settle(a, None, False, 4)
        self.assertNotIn(mock.call('None.0'), a.editor.yview.call_args_list)


if __name__ == '__main__':
    unittest.main()
