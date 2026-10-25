# -*- coding: utf-8 -*-
"""Choosing a candidate (re-conversion) is one undo step (2026-10-23 うにさん「再変換で候補から選んだあと、1回
アンドゥすると再変換した範囲が空欄になる。再度アンドゥすると元に戻るが、これは1回で元に戻す」).

Tk puts a separator between a delete and an insert by itself, so the word was taken out by one undo and put
back by the next. Now one undo brings the word back and one redo the candidate again — in the memo and in
Quick Input, and also for 「元に戻す」. The Text goes through the app's own command (observe_text with the
Unicode undo wrapper), as in the app."""
import unittest
from types import SimpleNamespace
import tkinter as tk

import app
from analysis_work import observe_text

UNIT = dict(start=3, end=4, text='鏡', base='鏡', prev='', next='', reading='かがみ')


class ChooseUndoTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = self.box()
        a._quick_text = self.box()
        a._candidate_selection_unit = lambda row, unit, cand, widget: unit
        a.unified_autofix_on = lambda: False
        a._mark_typed = lambda *args: None
        a._invalidate_units_cache = a._invalidate_analysis_cache = lambda: None
        a._supersede_prior_choice = lambda *args: None
        a.choices = SimpleNamespace(record=lambda *args: None, save=lambda: None)
        a._choice_reading = lambda unit, cand: ''
        a._remember_recent = lambda surface: None
        a._editor_changes, a._quick_changes = [], []
        a.status = SimpleNamespace(config=lambda **kw: None)
        a._retain_contextual_selection = lambda *args: None
        a._on_change = a._analyze_quick = lambda: None
        a._forget_chain = lambda *args: None
        a._dropdown_via_f2 = True

    def tearDown(self):
        self.root.destroy()

    def box(self):
        t = tk.Text(self.root, undo=True, autoseparators=True)
        observe_text(t)
        t.insert('1.0', '今日は鏡が良い')
        t.edit_reset(); t.edit_separator()
        return t

    def check(self, widget, choose):
        choose()
        self.assertEqual(widget.get('1.0', 'end-1c'), '今日は機嫌が良い')
        widget.edit_undo()
        self.assertEqual(widget.get('1.0', 'end-1c'), '今日は鏡が良い')       # one undo: the word is back
        widget.edit_redo()
        self.assertEqual(widget.get('1.0', 'end-1c'), '今日は機嫌が良い')     # one redo: the candidate again

    def test_the_memo(self):
        self.check(self.a.editor, lambda: self.a._editor_choose_word(1, dict(UNIT), {'surface': '機嫌'}))

    def test_quick_input(self):
        self.check(self.a._quick_text, lambda: self.a._quick_choose_word(1, dict(UNIT), {'surface': '機嫌'}))

    def test_putting_the_word_back_is_one_step_too(self):
        a = self.a
        a._editor_choose_word(1, dict(UNIT), {'surface': '機嫌'})
        a.editor.edit_separator()
        a._editor_undo_choice(1, dict(UNIT, end=5), '鏡')              # 「元に戻す」 from the list
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '今日は鏡が良い')
        a.editor.edit_undo()
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '今日は機嫌が良い')
        a._quick_choose_word(1, dict(UNIT), {'surface': '機嫌'})
        a._quick_text.edit_separator()
        a._quick_undo_choice(1, dict(UNIT, end=5), '鏡')
        a._quick_text.edit_undo()
        self.assertEqual(a._quick_text.get('1.0', 'end-1c'), '今日は機嫌が良い')


if __name__ == '__main__':
    unittest.main()
