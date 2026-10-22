# -*- coding: utf-8 -*-
"""Enter in quote mode with nothing selected ends the quote and makes a new line (2026-10-22).

うにさん「変換中にF1を間違えて押すと、そのあとエンターしても引用モードで改行できないことになる
ので、引用モードで無選択エンターしたら引用を終える」. A selection is still quoted, and a written
formula (「＝」 calculation) still takes the Enter. Withdrawn root; no clipboard."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk

import app, ime_watch


class QuoteEnterTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root); a.result_view = tk.Text(self.root); a._quick_text = None
        a.editor.insert('1.0', '前の文\n引用元の語'); a.editor.mark_set('insert', '1.3')
        a._pick_mode = 'click'; a._pick_calculate = False
        a._close_bulk_insert_from_escape = lambda event: False
        a._end_pick_mode = Mock(side_effect=lambda **kw: setattr(a, '_pick_mode', None))
        a._pick_insert = Mock()

    def tearDown(self):
        self.root.destroy()

    def enter(self, widget=None):
        event = SimpleNamespace(widget=widget or self.a.editor, keysym='Return', char='\r', state=0)
        with patch.object(ime_watch, 'composition_active', return_value=False):
            return self.a._on_pick_mode_keypress(event)

    def test_nothing_selected_ends_the_quote_and_lets_the_newline_through(self):
        self.assertIsNone(self.enter())                  # None: the Text class inserts the newline
        self.a._end_pick_mode.assert_called_once_with(keep_equals=True)
        self.assertIsNone(self.a._pick_mode)
        self.a._pick_insert.assert_not_called()

    def test_a_selection_is_still_quoted(self):
        self.a.editor.tag_add('sel', '2.0', '2.3')
        self.assertEqual(self.enter(), 'break')
        self.a._pick_insert.assert_called_once_with('引用元')
        self.a._end_pick_mode.assert_not_called()

    def test_a_written_formula_still_takes_the_enter(self):
        self.a._finish_pick_calculation = Mock(return_value=True)
        self.assertEqual(self.enter(), 'break')
        self.a._end_pick_mode.assert_not_called()

    def test_words_after_an_accidental_f1_end_the_quote_but_a_formula_attempt_does_not(self):
        a = self.a
        a._pick_calculate = True; a._pick_target = 'editor'; a.session = None
        a.editor_source_text = lambda: a.editor.get('1.0', 'end-1c')
        a._source_editor_position = lambda mark, source=None, edge=None: tuple(map(int, a.editor.index(mark).split('.')))
        a._pick_mark_edge = lambda mark: None
        a.status = Mock()
        for typed, handled in (('かんじ', False), ('2²', True)):
            with self.subTest(typed=typed):
                a.editor.delete('1.0', 'end'); a.editor.insert('1.0', '前' + typed)
                a.editor.mark_set(a._PICK_MARK, '1.1'); a.editor.mark_gravity(a._PICK_MARK, 'left')
                a.editor.mark_set(a._PICK_CALC_END, '1.end'); a.editor.mark_set('insert', '1.end')
                self.assertEqual(bool(a._finish_pick_calculation(a.editor)), handled)

    def test_calculation_reports_whether_it_handled_the_enter(self):
        self.assertFalse(self.a._finish_pick_calculation(self.a.editor))   # no formula started


if __name__ == '__main__':
    unittest.main()
