# -*- coding: utf-8 -*-
"""Two quick clicks on two tabs do not reorder them (2026-10-25 うにさん「タブをクリックしてすぐ別のタブをクリックすると、
意図せずタブの位置が入れ替わることがある」).

A drag began after 12 px of movement with the button held, at any speed: a quick click that is still held while the
pointer already heads for the next tab (and Tk delivers that movement late, after the switch the press started)
was taken as dragging the first tab onto the second one's seat. A drag now also needs the button held for
TAB_DRAG_HOLD_MS (Tk's own event times, so a slow switch does not shorten it). No windows: the seats are stubs."""
import unittest
from types import SimpleNamespace

import app


class _Seat:
    def __init__(self, left, width):
        self.left, self.width = left, width

    def winfo_rootx(self):
        return self.left

    def winfo_width(self):
        return self.width


class QuickClickTests(unittest.TestCase):
    def setUp(self):
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.session = SimpleNamespace(tabs=['A', 'B', 'C'], active=0)
        a._tab_widgets = [{'frame': _Seat(0, 100)}, {'frame': _Seat(100, 100)}, {'frame': _Seat(200, 100)}]
        a._refresh_tab_bar = lambda: None
        self.saved = []
        a._schedule_session_save = lambda: self.saved.append(True)

    def press(self, x, t, index):
        self.a._on_tab_press(SimpleNamespace(x_root=x, time=t), index)

    def move(self, x, t):
        self.a._on_tab_drag_motion(SimpleNamespace(x_root=x, time=t))

    def release(self):
        self.a._on_tab_drag_end(SimpleNamespace())

    def test_a_quick_click_while_heading_for_the_next_tab_does_not_reorder(self):
        # click A (still held 60 ms later, the pointer already 100 px on, over B), then click B
        self.press(50, 1000, 0)
        self.move(150, 1060)
        self.release()
        self.press(150, 1200, 1)
        self.release()
        self.assertEqual(self.a.session.tabs, ['A', 'B', 'C'])
        self.assertEqual(self.saved, [])

    def test_a_held_drag_still_reorders(self):
        self.press(50, 1000, 0)
        self.move(60, 1100)                  # held, moved a little
        self.move(150, 1000 + self.a.TAB_DRAG_HOLD_MS)
        self.release()
        self.assertEqual(self.a.session.tabs, ['B', 'A', 'C'])
        self.assertEqual(self.a.session.active, 1)
        self.assertEqual(self.saved, [True])

    def test_a_quick_move_that_is_then_held_becomes_a_drag(self):
        self.press(50, 1000, 0)
        self.move(150, 1050)                 # too soon: not yet a drag
        self.assertEqual(self.a.session.tabs, ['A', 'B', 'C'])
        self.move(250, 1300)                 # still held: now it is
        self.release()
        self.assertEqual(self.a.session.tabs, ['B', 'C', 'A'])

    def test_events_without_times_keep_the_distance_rule(self):
        self.a._on_tab_press(SimpleNamespace(x_root=50, time=0), 0)
        self.a._on_tab_drag_motion(SimpleNamespace(x_root=150, time=0))
        self.release()
        self.assertEqual(self.a.session.tabs, ['B', 'A', 'C'])


if __name__ == '__main__':
    unittest.main()
