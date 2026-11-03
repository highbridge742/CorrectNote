# -*- coding: utf-8 -*-
"""The tab strip: a new tab comes into view, and a tab being dragged does not move under the mouse (2026-11-03)."""
import time
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app as app_module

App = app_module.CorrectNoteApp


class Strip:
    """The strip's own methods on real widgets, off-screen."""
    TAB_DRAG_THRESHOLD = App.TAB_DRAG_THRESHOLD
    TAB_DRAG_HOLD_MS = App.TAB_DRAG_HOLD_MS
    TAB_DRAG_STALE_S = App.TAB_DRAG_STALE_S
    TAB_DROP_QUIET_S = App.TAB_DROP_QUIET_S
    TAB_DRAG_EDGE_PX = App.TAB_DRAG_EDGE_PX
    TAB_DRAG_EDGE_STEP_PX = App.TAB_DRAG_EDGE_STEP_PX
    TAB_DRAG_EDGE_MS = App.TAB_DRAG_EDGE_MS
    TAB_REVEAL_RETRY_MS = App.TAB_REVEAL_RETRY_MS
    TAB_REVEAL_TRIES = App.TAB_REVEAL_TRIES
    TAB_REVEAL_EDGE_SHARE = App.TAB_REVEAL_EDGE_SHARE
    _queue_tab_reveal = App._queue_tab_reveal
    _reveal_active_tab = App._reveal_active_tab
    _tab_drag_active = App._tab_drag_active
    _on_tab_press = App._on_tab_press
    _on_tab_drag_motion = App._on_tab_drag_motion
    _on_tab_drag_end = App._on_tab_drag_end
    _tab_drag_place = App._tab_drag_place
    _tab_drag_edge_step = App._tab_drag_edge_step
    _tab_drag_edge_tick = App._tab_drag_edge_tick
    _left_button_is_up = staticmethod(App._left_button_is_up)

    def __init__(self, root, count):
        self.root = root
        self._tab_viewport = tk.Canvas(root, highlightthickness=0, height=29, width=400)
        self._tab_viewport.pack(fill='x')
        self.tab_bar = tk.Frame(self._tab_viewport)
        self._tab_viewport.create_window(0, 0, window=self.tab_bar, anchor='nw')
        for widget in (self._tab_viewport, self.tab_bar):
            widget.bind('<Configure>', self._queue_tab_reveal)
        self.session = NS(tabs=list(range(count)), active=1)
        self._tab_widgets = []
        self.saved = 0
        self.rebuild()

    def rebuild(self):
        for widget in self.tab_bar.winfo_children():
            widget.destroy()
        self._tab_widgets = []
        for k in self.session.tabs:
            frame = tk.Frame(self.tab_bar)
            frame.pack(side='left', padx=(0, 3))
            tk.Label(frame, text='タブ%03d' % k, padx=10).pack()
            self._tab_widgets.append(dict(frame=frame))
        self._queue_tab_reveal()

    def _refresh_tab_bar(self):
        self._queue_tab_reveal()

    def _schedule_session_save(self):
        self.saved += 1

    def left(self):
        return self._tab_viewport.canvasx(0)

    def active_seen(self):
        frame = self._tab_widgets[self.session.active]['frame']
        at = frame.winfo_rootx() - self._tab_viewport.winfo_rootx()
        return at >= 0 and at + frame.winfo_width() <= self._tab_viewport.winfo_width()

    def x_of(self, index):
        frame = self._tab_widgets[index]['frame']
        return frame.winfo_rootx() + frame.winfo_width() // 2


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0)
        self.root.geometry('400x60+10000+10000')
        self.strip = Strip(self.root, 20)
        self.pump()

    def tearDown(self):
        self.root.destroy()

    def pump(self, seconds=.15):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(.003)


class NewTab(Base):
    def test_a_new_tab_comes_into_view(self):
        strip = self.strip
        self.assertFalse(strip._tab_widgets[-1]['frame'].winfo_rootx() - strip._tab_viewport.winfo_rootx() < 400)
        strip.session.tabs.append(20); strip.session.active = 20
        strip.rebuild()
        self.pump()
        self.assertTrue(strip.active_seen())

    def test_a_reveal_queued_before_the_tab_was_added(self):
        strip = self.strip
        strip._queue_tab_reveal()       # waiting already: it runs before the new tab has its width
        strip.session.tabs.append(20); strip.session.active = 20
        strip.rebuild()
        self.pump()
        self.assertTrue(strip.active_seen())

    def test_the_tries_end(self):
        strip = self.strip
        with mock.patch.object(strip.tab_bar, 'winfo_width', return_value=1):
            strip._queue_tab_reveal()
            self.pump(.5)
        self.assertLessEqual(strip._tab_reveal_tries, strip.TAB_REVEAL_TRIES)
        self.assertIsNone(strip._tab_reveal_job)


class Middle(Base):
    def scrolled_to(self, index):
        """Tab index in the middle of a strip already scrolled away from its end."""
        strip = self.strip
        strip.session.active = index
        self.pump()
        frame = strip._tab_widgets[index]['frame']
        width = strip._tab_viewport.winfo_width()
        strip._tab_viewport.xview_moveto((frame.winfo_x() + frame.winfo_width() / 2 - width / 2) / strip.tab_bar.winfo_reqwidth())
        self.pump()
        return strip.left()

    def select(self, index):
        self.strip.session.active = index
        self.strip._queue_tab_reveal()
        self.pump()

    def in_middle(self, index):
        strip = self.strip
        frame = strip._tab_widgets[index]['frame']
        at = frame.winfo_rootx() - strip._tab_viewport.winfo_rootx()
        width = strip._tab_viewport.winfo_width()
        return at >= width * .2 and at + frame.winfo_width() <= width * .8

    def test_next_to_the_middle_does_not_move(self):
        before = self.scrolled_to(10)
        self.assertTrue(self.in_middle(10))
        self.select(10)
        self.assertEqual(self.strip.left(), before)

    def test_a_tab_in_the_edge_share_is_centred(self):
        before = self.scrolled_to(10)
        strip = self.strip
        far = next(k for k in range(11, 20) if not self.in_middle(k) and strip._tab_widgets[k]['frame'].winfo_rootx() - strip._tab_viewport.winfo_rootx() < strip._tab_viewport.winfo_width())
        self.select(far)
        self.assertGreater(strip.left(), before)
        self.assertTrue(self.in_middle(far))

    def test_a_hidden_tab_is_centred(self):
        self.scrolled_to(3)
        self.select(15)
        self.assertTrue(self.in_middle(15))

    def test_one_move_only(self):
        strip = self.strip
        self.scrolled_to(3)
        strip.session.active = 15
        with mock.patch.object(strip._tab_viewport, 'xview_moveto', wraps=strip._tab_viewport.xview_moveto) as move:
            strip._queue_tab_reveal()
            self.pump()
        self.assertEqual(move.call_count, 1)


class QuickClick(unittest.TestCase):
    """The times are of the mouse, not of when a slow tab switch let them be handled."""
    def app(self):
        a = App.__new__(App)
        a.session = NS(tabs=['A', 'B', 'C'], active=0)
        seat = lambda left: NS(winfo_rootx=lambda: left, winfo_width=lambda: 100)
        a._tab_widgets = [dict(frame=seat(0)), dict(frame=seat(100)), dict(frame=seat(200))]
        a._refresh_tab_bar = lambda: None
        a._tab_viewport = None
        return a

    def test_a_click_while_moving_does_not_swap(self):
        a = self.app()
        a._on_tab_press(NS(x_root=50, time=1000), 0)
        a._on_tab_drag_motion(NS(x_root=150, time=1080))
        self.assertEqual(a.session.tabs, ['A', 'B', 'C'])

    def test_a_held_drag_swaps(self):
        a = self.app()
        a._on_tab_press(NS(x_root=50, time=1000), 0)
        a._on_tab_drag_motion(NS(x_root=150, time=1300))
        self.assertEqual(a.session.tabs, ['B', 'A', 'C'])

    def test_motion_after_the_button_is_up_does_not_swap(self):
        a = self.app()
        a._on_tab_press(NS(x_root=50, time=1000), 0)
        with mock.patch.object(App, '_left_button_is_up', return_value=True):
            a._on_tab_drag_motion(NS(x_root=150, time=1300))
        self.assertEqual(a.session.tabs, ['A', 'B', 'C'])
        self.assertFalse(a._tab_drag['moved'])

    def test_a_small_wobble_does_not_swap(self):
        a = self.app()
        a._on_tab_press(NS(x_root=95, time=1000), 0)
        a._on_tab_drag_motion(NS(x_root=105, time=1300))       # under the threshold, into the next seat
        self.assertEqual(a.session.tabs, ['A', 'B', 'C'])

    def test_just_inside_the_next_seat_does_not_swap(self):
        a = self.app()
        a._on_tab_press(NS(x_root=95, time=1000), 0)
        a._on_tab_drag_motion(NS(x_root=110, time=1300))       # over the threshold, not past the seat's middle
        self.assertEqual(a.session.tabs, ['A', 'B', 'C'])
        a._on_tab_drag_motion(NS(x_root=150, time=1350))
        self.assertEqual(a.session.tabs, ['B', 'A', 'C'])

    def test_back_past_the_middle(self):
        a = self.app()
        a.session.active = 2
        a._on_tab_press(NS(x_root=250, time=1000), 2)
        a._on_tab_drag_motion(NS(x_root=180, time=1300))
        self.assertEqual(a.session.tabs, ['A', 'B', 'C'])
        a._on_tab_drag_motion(NS(x_root=140, time=1350))
        self.assertEqual(a.session.tabs, ['A', 'C', 'B'])

    def test_the_strip_moving_is_not_the_mouse_moving(self):
        a = self.app()
        a._on_tab_press(NS(x_root=50, time=1000), 0)
        a._tab_widgets[1]['frame'].winfo_rootx = lambda: 0       # the seats slide under a still pointer
        a._tab_widgets[0]['frame'].winfo_rootx = lambda: -100
        a._on_tab_drag_motion(NS(x_root=50, time=1300))
        self.assertEqual(a.session.tabs, ['A', 'B', 'C'])
        self.assertFalse(a._tab_drag['moved'])

    def test_a_tk_event_reads_the_button(self):
        import tkinter
        event = tkinter.Event()
        with mock.patch('ctypes.windll') as windll:
            windll.user32.GetSystemMetrics.return_value = 0
            windll.user32.GetAsyncKeyState.return_value = 0
            self.assertTrue(App._left_button_is_up(event))
            windll.user32.GetAsyncKeyState.assert_called_with(0x01)
            windll.user32.GetAsyncKeyState.return_value = -32768
            self.assertFalse(App._left_button_is_up(event))
            windll.user32.GetSystemMetrics.return_value = 1      # the buttons swapped in Windows
            App._left_button_is_up(event)
            windll.user32.GetAsyncKeyState.assert_called_with(0x02)

    def test_a_made_event_says_nothing_about_the_button(self):
        self.assertFalse(App._left_button_is_up(NS()))


class Drag(Base):
    def press(self, index):
        self.strip.session.active = index
        self.strip._queue_tab_reveal()       # the press selects the tab first (_switch_tab)
        self.strip._on_tab_press(NS(x_root=self.strip.x_of(index), time=1000), index)

    def motion(self, x, at=2000):
        self.strip._on_tab_drag_motion(NS(x_root=x, time=at))

    def test_a_press_does_not_move_the_strip_under_the_mouse(self):
        before = self.strip.left()
        self.press(4)
        self.pump()
        self.assertEqual(self.strip.left(), before)

    def test_only_a_press_centres_the_tab_when_released(self):
        before = self.strip.left()
        self.press(5)     # in the edge share
        self.pump()
        self.strip._on_tab_drag_end(NS())
        self.pump()
        self.assertNotEqual(self.strip.left(), before)
        self.assertTrue(self.strip.active_seen())

    def test_swapping_does_not_move_the_strip(self):
        strip = self.strip
        before = strip.left()
        self.press(1)
        target = strip.x_of(3)
        self.motion(target)
        self.pump()
        self.assertEqual(strip.session.active, 3)
        self.assertEqual(strip.left(), before)
        self.assertEqual(strip.session.tabs[3], 1)

    def test_a_drop_in_view_leaves_the_strip(self):
        strip = self.strip
        before = strip.left()
        self.press(1)
        self.motion(strip.x_of(3))
        self.pump()
        strip._on_tab_drag_end(NS())
        self.pump()
        self.assertEqual(strip.left(), before)
        self.assertEqual(strip.saved, 1)

    def test_near_the_edge_the_strip_goes_a_little_at_a_time(self):
        strip = self.strip
        self.press(1)
        right_edge = strip._tab_viewport.winfo_rootx() + strip._tab_viewport.winfo_width() - 5
        before = strip.left()
        self.motion(right_edge)
        self.assertLessEqual(strip.left() - before, strip.TAB_DRAG_EDGE_STEP_PX + 1)
        self.pump(.3)
        self.assertGreater(strip.left(), before)
        self.assertGreater(strip.session.active, 1)
        strip._on_tab_drag_end(NS())
        moved = strip.left()
        self.pump(.2)
        self.assertEqual(strip.left(), moved)       # stops when released
        self.assertTrue(strip.active_seen())

    def test_a_tab_dropped_half_hidden_comes_just_into_view(self):
        strip = self.strip
        self.press(1)
        strip._tab_drag['moved'] = True
        strip.session.active = 5
        frame = strip._tab_widgets[5]['frame']
        strip._tab_viewport.xview_moveto((frame.winfo_x() + 10) / strip.tab_bar.winfo_reqwidth())
        self.pump()
        self.assertFalse(strip.active_seen())
        strip._on_tab_drag_end(NS())
        self.pump()
        self.assertTrue(strip.active_seen())
        self.assertEqual(frame.winfo_rootx(), strip._tab_viewport.winfo_rootx())    # only as far as needed

    def test_a_lost_release_does_not_hold_the_strip_for_ever(self):
        strip = self.strip
        self.press(5)
        strip._tab_drag['seen'] = time.monotonic() - strip.TAB_DRAG_STALE_S - 1
        strip._queue_tab_reveal()
        self.pump()
        self.assertTrue(strip.active_seen())
        self.assertGreater(strip.left(), 0)


if __name__ == '__main__':
    unittest.main()
