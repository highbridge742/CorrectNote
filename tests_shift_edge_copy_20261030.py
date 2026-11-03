# -*- coding: utf-8 -*-
"""Shift+Home / Shift+End once more at the line's edge copies the selection (2026-10-30 うにさん
「Shift+Homeを2回連続、またはShift+Endを2回連続押したら、選択範囲をコピーする」)."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import tkinter as tk

import app


class ShiftEdgeCopyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root, width=40)
        self.text.insert('1.0', '一行目の文です\n二行目')
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a._copy_focused_selection = Mock()

    def tearDown(self):
        self.root.destroy()

    def press(self, key):
        return self.a._on_shift_edge_copy(SimpleNamespace(widget=self.text, keysym=key))

    def test_second_press_at_the_line_start_copies(self):
        t = self.text
        t.mark_set('insert', '1.3')
        self.assertIsNone(self.press('Home'))                 # no selection: Tk moves and selects as usual
        t.tag_add('sel', '1.0', '1.3'); t.mark_set('insert', '1.0')
        self.assertEqual(self.press('Home'), 'break')        # already at the start: the selection is copied
        self.a._copy_focused_selection.assert_called_once()
        self.assertEqual(t.get('sel.first', 'sel.last'), '一行目')   # the selection stays

    def test_second_press_at_the_line_end_copies(self):
        t = self.text
        t.tag_add('sel', '1.3', '1.end'); t.mark_set('insert', '1.5')
        self.assertIsNone(self.press('End'))                  # not at the end yet: Tk extends the selection
        self.a._copy_focused_selection.assert_not_called()
        t.mark_set('insert', '1.end')
        self.assertEqual(self.press('End'), 'break')
        self.a._copy_focused_selection.assert_called_once()


if __name__ == '__main__':
    unittest.main()
