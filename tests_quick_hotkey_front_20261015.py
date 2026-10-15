# -*- coding: utf-8 -*-
"""簡易入力のショートカットで、開いているが前に無い簡易入力の窓を前に出す（2026-10-15）。

うにさん「簡易入力が開いているが非アクティブの時に、簡易入力を開くショートカットキーを
実行したら、簡易入力ウインドウをアクティブにする」。前は最小化していた。
"""
import tkinter as tk
import unittest
from unittest.mock import Mock

import app


class QuickHotkeyFrontTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.status = Mock()
        a._refresh_quick_hint = Mock()
        a._focus_quick_window = Mock()
        a._place_quick_window = Mock()
        a._quick_text = object()
        self.win = Mock()
        a._quick_win = self.win
        self.a = a

    def tearDown(self):
        self.root.destroy()

    def press(self, state, active):
        self.win.state.return_value = state
        self.a._quick_window_is_active = lambda win: active
        self.a._show_quick_capture('insert')

    def test_open_but_not_in_front_comes_forward(self):
        self.press('normal', active=False)
        self.a._focus_quick_window.assert_called_once()
        self.assertIs(self.a._focus_quick_window.call_args[0][0], self.win)
        self.win.iconify.assert_not_called()
        self.a.status.config.assert_called_with(text='簡易入力ウィンドウを前に出しました')

    def test_in_front_still_minimises(self):
        self.press('normal', active=True)
        self.win.iconify.assert_called_once()
        self.a._focus_quick_window.assert_not_called()

    def test_minimised_is_restored_as_before(self):
        import quick_selection
        saved = quick_selection.insert_selection
        quick_selection.insert_selection = lambda app_, value: None
        try:
            self.press('iconic', active=False)
        finally:
            quick_selection.insert_selection = saved
        self.win.deiconify.assert_called_once()
        self.a._focus_quick_window.assert_called_once()
        self.win.iconify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
