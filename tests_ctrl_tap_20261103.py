# -*- coding: utf-8 -*-
"""Ctrl twice: measured by when the keys were pressed, at any ordinary speed, busy or not (2026-11-03)."""
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import reinput
from reinput import ReInput, _key_ms


def key(name, at, state=0, keycode=0):
    return NS(keysym=name, time=at, state=state, keycode=keycode)


class Taps(unittest.TestCase):
    def setUp(self):
        self.r = ReInput.__new__(ReInput)
        self.r.state = None
        self.r._waiting = None
        self.r._down_at = self.r._released_at = None
        self.r._chord = False
        self.r.app = NS(_cursor_hider=None)
        self.r.composing = lambda: False
        self.r._reconvert_range_open = lambda: False
        self.r._selection_space = lambda event: False
        self.r.start = mock.Mock()

    def tap(self, down, up, name='Control_L'):
        self.r.on_press(key(name, down))
        self.r.on_release(key(name, up))

    def test_ordinary_speeds_open(self):
        for hold, gap in ((50, 120), (50, 60), (100, 250), (120, 300), (80, 400), (400, 100)):
            self.r.start.reset_mock(); self.r._forget_taps()
            self.tap(1000, 1000 + hold)
            self.tap(1000 + hold + gap, 1000 + 2 * hold + gap)
            self.r.start.assert_called_once()

    def test_too_slow(self):
        self.tap(1000, 1050); self.tap(1500, 1550)
        self.r.start.assert_not_called()

    def test_a_held_ctrl_does_not_count(self):
        self.tap(1000, 1500); self.tap(1600, 1650)
        self.r.start.assert_not_called()
        self.tap(1700, 1750)
        self.r.start.assert_called_once()

    def test_left_and_right(self):
        self.tap(1000, 1050, 'Control_L'); self.tap(1150, 1200, 'Control_R')
        self.r.start.assert_called_once()

    def test_autorepeat_keeps_the_first_press(self):
        for at in (1000, 1300, 1330, 1360):
            self.r.on_press(key('Control_L', at))
        self.r.on_release(key('Control_L', 1500))
        self.assertIsNone(self.r._released_at)

    def test_a_key_let_go_between_does_not_reset(self):
        self.tap(1000, 1050)
        self.r.on_release(key('a', 1060))
        self.tap(1150, 1200)
        self.r.start.assert_called_once()

    def test_a_key_pressed_between_resets(self):
        self.tap(1000, 1050)
        self.r.on_press(key('a', 1060))
        self.tap(1150, 1200)
        self.r.start.assert_not_called()

    def test_ctrl_and_a_key_is_not_a_tap(self):
        for at in (1000, 1200):
            self.r.on_press(key('Control_L', at))
            self.r.on_press(key('c', at + 10, state=4))
            self.r.on_release(key('c', at + 20, state=4))
            self.r.on_release(key('Control_L', at + 30))
        self.r.start.assert_not_called()

    def test_ctrl_press_not_seen_counts_by_its_release(self):
        self.r.on_release(key('Control_L', 1050))
        self.r.on_release(key('Control_L', 1200))
        self.r.start.assert_called_once()

    def test_ctrl_as_the_key_the_ime_took(self):
        for down, up in ((1000, 1050), (1150, 1200)):
            self.r.on_press(key('??', down, keycode=229))
            self.r.on_release(key('Control_L', up))
        self.r.start.assert_called_once()

    def test_a_busy_window_does_not_stretch_it(self):
        # handled long after, but pressed at ordinary speed: the times are of the keys
        self.tap(1000, 1050)
        with mock.patch('time.monotonic', return_value=999.0):
            self.tap(1200, 1250)
        self.r.start.assert_called_once()

    def test_the_clock_going_round(self):
        top = 0xFFFFFFFF
        self.tap(top - 100, top - 50); self.tap(top + 50 & top, top + 100 & top)
        self.r.start.assert_called_once()


class Times(unittest.TestCase):
    def test_a_made_event_uses_its_time(self):
        self.assertEqual(_key_ms(NS(time=1234)), 1234)

    def test_no_time_uses_the_clock(self):
        with mock.patch('time.monotonic', return_value=5.0):
            self.assertEqual(_key_ms(NS()), 5000)

    def test_a_tk_event_uses_the_message_time(self):
        import tkinter
        event = tkinter.Event(); event.time = 9999
        with mock.patch('ctypes.windll') as windll:
            windll.user32.GetMessageTime.return_value = 7777
            self.assertEqual(_key_ms(event), 7777)


if __name__ == '__main__':
    unittest.main()
