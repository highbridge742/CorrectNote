# -*- coding: utf-8 -*-
"""The edited text is drawn at once, even while analysis timers keep Tk from
going idle (2026-10-18: an IME commit vanished and appeared a moment later)."""
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_work_app


class DrawEditTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = tk.Text(self.root)
        self.editor.pack()
        self.a = SimpleNamespace(root=self.root, editor=self.editor)

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root', 'editor')

    def test_one_draw_at_the_next_turn_before_later_timers(self):
        order = []
        with patch.object(self.editor, 'update_idletasks', side_effect=lambda: order.append('draw')):
            # a timer that keeps coming due (as the 5ms analysis polls do)
            def busy():
                order.append('busy')
                if order.count('busy') < 5:
                    self.root.after(0, busy)
            analysis_work_app.draw_soon(self.a)
            analysis_work_app.draw_soon(self.a)          # one draw per pending edit
            self.root.after(0, busy)
            end = time.monotonic() + 2
            while time.monotonic() < end and order.count('busy') < 5:
                self.root.update()
        self.assertEqual(order.count('draw'), 1)
        self.assertLess(order.index('draw'), order.index('busy'))
        self.assertIsNone(self.a._draw_edit_job)

    def test_the_change_handler_draws_a_pending_edit_first(self):
        with patch.object(self.editor, 'update_idletasks') as draw:
            analysis_work_app.draw_now(self.a)               # nothing pending: nothing to do
            draw.assert_not_called()
            analysis_work_app.draw_soon(self.a)
            analysis_work_app.draw_now(self.a)
            draw.assert_called_once_with()
            self.assertIsNone(self.a._draw_edit_job)
            self.root.update()                               # the cancelled turn does not draw again
            draw.assert_called_once_with()

    def test_without_a_window_nothing_happens(self):
        a = SimpleNamespace(editor=None, root=self.root)
        analysis_work_app.draw_soon(a)
        self.assertFalse(getattr(a, '_draw_edit_job', None))


if __name__ == '__main__':
    unittest.main()
