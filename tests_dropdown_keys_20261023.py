# -*- coding: utf-8 -*-
"""Keys in the reconversion list (2026-10-23 うにさん).

1. Space chooses the selected candidate (as Enter does), also the IME's full-width space.
2. 「候補一覧が出ていて語が選択された状態で文字を打ったら、一覧を閉じ、選択範囲の語を消して、その文字
   から入力を始める」: the selected word is replaced by what is typed. The characters the IME commits
   arrive one by one, so the list stays a moment and the rest go to the same place before it closes
   (none of them lost). Without an open list, typing still goes after the range (C-1).
Withdrawn root."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk

import app


class DropdownKeyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root; a._dropdown = None; a._dropdown_text = ''
        a.editor = tk.Text(self.root, undo=True); a.editor.pack()
        a.editor.insert('1.0', '文字入力を性格に反映する')
        a._f2_editable_target = lambda: (a.editor, 1, 5, 7)
        a._mark_typed = Mock(); a._after_f2_edit = Mock()

    def tearDown(self):
        self.root.update()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(.005)

    def open_list(self, chosen):
        items = [('「性格」', None), ('  正確', lambda: chosen.append('正確'))]
        with patch.object(app, 'monitor_work_area', return_value=(0, 0, 1920, 1040)):
            self.a._make_dropdown(items, 100, 100)
        lb = self.a._dropdown_parts['lb']
        lb.selection_set(1)
        return lb

    def test_space_chooses_the_selected_candidate(self):
        chosen = []
        lb = self.open_list(chosen)
        self.assertTrue(lb.bind('<space>'))
        self.assertEqual(self.a._dropdown_pick(), 'break')
        self.assertEqual(chosen, ['正確'])
        self.assertIsNone(self.a._dropdown)
        # The IME's full-width space chooses too
        chosen.clear(); lb = self.open_list(chosen)
        self.assertEqual(self.a._on_dropdown_typed(SimpleNamespace(char='　')), 'break')
        self.assertEqual(chosen, ['正確'])

    def test_typing_replaces_the_selected_word_and_keeps_every_character(self):
        chosen = []
        self.open_list(chosen)
        for ch in 'てすと':           # an IME commit arrives as one key press per character
            self.assertEqual(self.a._on_dropdown_typed(SimpleNamespace(char=ch)), 'break')
        self.assertEqual(self.a.editor.get('1.0', 'end-1c'), '文字入力をてすとに反映する')
        self.assertEqual(self.a.editor.index('insert'), '1.8')
        self.assertIsNotNone(self.a._dropdown)               # stays a moment for the rest
        self.pump(.3)
        self.assertIsNone(self.a._dropdown)
        self.assertEqual(chosen, [])
        self.a._after_f2_edit.assert_called_once_with(self.a.editor)
        # Undo takes back the typing and gives the word back
        self.a.editor.edit_undo()
        self.assertEqual(self.a.editor.get('1.0', 'end-1c'), '文字入力を性格に反映する')

    def test_keys_that_are_not_characters_are_left_alone(self):
        self.open_list([])
        self.assertIsNone(self.a._on_dropdown_typed(SimpleNamespace(char='')))
        self.assertIsNone(self.a._on_dropdown_typed(SimpleNamespace(char='\t')))
        self.assertEqual(self.a.editor.get('1.0', 'end-1c'), '文字入力を性格に反映する')
        self.a._close_dropdown(keep_target=True)

    def test_without_the_list_typing_still_goes_after_the_range(self):
        # C-1 (no list open): the word stays, the character goes after it
        self.a._dropdown = None; self.a._f2_focus_target = dict(widget=self.a.editor)
        self.a._close_dropdown = Mock()
        self.assertEqual(self.a._on_f2_range_keypress(SimpleNamespace(char='を')), 'break')
        self.assertEqual(self.a.editor.get('1.0', 'end-1c'), '文字入力を性格をに反映する')


if __name__ == '__main__':
    unittest.main()
