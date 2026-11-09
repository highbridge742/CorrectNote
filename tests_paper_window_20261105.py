# -*- coding: utf-8 -*-
"""The picture behind the text without pasting it row by row (2026-11-05 うにさん: fixed to the window, so no need to redraw it).
No window: what is decided, and the way back to the old form when showing through cannot be used."""
import unittest
from unittest import mock

import appearance as ap
import paper_window as pw


class Decide(unittest.TestCase):
    def test_child_windows_can_show_through_from_windows_8(self):
        self.assertFalse(pw.available((6, 1), 'win32'))
        self.assertTrue(pw.available((6, 2), 'win32'))
        self.assertTrue(pw.available((10, 0), 'win32'))
        self.assertFalse(pw.available((10, 0), 'linux'))

    def test_colour_key(self):
        self.assertEqual(pw.colorref((0xF0F0, 0xE0E0, 0x1010)), 0x10E0F0)

    def test_every_mouse_message_goes_on(self):
        for message in (0x200, 0x201, 0x202, 0x203, 0x204, 0x205, 0x206, 0x207, 0x208, 0x209, 0x20A, 0x20B, 0x20C, 0x20D, 0x20E):
            self.assertIn(message, pw.MOUSE_MESSAGES)
        self.assertNotIn(0x20F, pw.MOUSE_MESSAGES)
        self.assertNotIn(0x233, pw.MOUSE_MESSAGES)      # the drop is the main window's

    def test_nothing_to_call_means_false(self):
        with mock.patch.object(pw, '_load', return_value=None):
            self.assertFalse(pw.show_through(1, 0))
            self.assertFalse(pw.attach_back(1, 2))
            pw.stop_showing_through(1)
            pw.detach_back(1)
            pw.repaint(1)


class FakeText:
    def __init__(self):
        self.master = self
        self.bound = []
        self.tk = mock.Mock()

    def bind(self, *a, **k):
        self.bound.append(a)

    def winfo_rgb(self, colour):
        return (0xF000, 0xF000, 0xED00)

    def cget(self, name):
        return '#f0f0ed' if name == 'background' else ''

    def winfo_id(self):
        return 1234

    def after(self, *a):
        return 'job'


def paper():
    p = ap.Paper(FakeText())
    p.decor, p.color, p.bg = 'nami', '#d0d0cc', '#f0f0ed'
    return p


class WayBack(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ap.Paper, 'SHOW_THROUGH', True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_switch_keeps_the_old_form(self):
        p = paper()
        with mock.patch.object(ap.Paper, 'SHOW_THROUGH', False), mock.patch.object(pw, 'show_through') as shown:
            self.assertFalse(p._enter_through())
        shown.assert_not_called()

    def test_no_decoration_does_not_show_through(self):
        p = paper()
        p.decor = None
        with mock.patch.object(pw, 'show_through') as shown:
            self.assertFalse(p._enter_through())
        shown.assert_not_called()

    def test_an_old_windows_keeps_the_old_form(self):
        p = paper()
        with mock.patch.object(pw, 'available', return_value=False), mock.patch.object(pw, 'show_through') as shown:
            self.assertFalse(p._enter_through())
            self.assertFalse(p._enter_through())
        shown.assert_not_called()
        self.assertTrue(p._through_failed)

    def test_a_failure_goes_back_for_good(self):
        for failing in ('attach_back', 'show_through'):
            p = paper()
            p._make_back = lambda: mock.Mock(winfo_id=lambda: 5)
            others = dict(attach_back=True, show_through=True)
            others[failing] = False
            with mock.patch.object(pw, 'available', return_value=True), mock.patch.object(pw, 'detach_back') as detached, \
                    mock.patch.object(pw, 'attach_back', return_value=others['attach_back']), \
                    mock.patch.object(pw, 'show_through', return_value=others['show_through']):
                self.assertFalse(p._enter_through())
                self.assertFalse(p._through)
                self.assertTrue(p._through_failed)
                self.assertIsNone(p._back)
                self.assertFalse(p._enter_through())
            detached.assert_called_once()

    def test_a_theme_change_moves_the_colour(self):
        p = paper()
        p._make_back = lambda: mock.Mock(winfo_id=lambda: 5)
        p._drop_all = lambda: None
        with mock.patch.object(pw, 'available', return_value=True), mock.patch.object(pw, 'attach_back', return_value=True), \
                mock.patch.object(pw, 'show_through', return_value=True) as shown:
            self.assertTrue(p._enter_through())
            first = shown.call_count
            self.assertTrue(p._enter_through())
            self.assertEqual(shown.call_count, first)      # nothing changed: not called again
            p.t.winfo_rgb = lambda colour: (0x1000, 0x1000, 0x1000)
            self.assertTrue(p._enter_through())
            self.assertEqual(shown.call_count, first + 1)
            self.assertEqual(p._through_key, 0x101010)

    def test_scrolling_does_nothing_while_showing_through(self):
        p = paper()
        p._through = True
        p.flush = mock.Mock(); p.queue = mock.Mock()
        p._on_scrolled(); p._on_changed(); p._on_tagged()
        p.flush.assert_not_called()
        p.queue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
