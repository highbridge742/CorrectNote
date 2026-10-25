# -*- coding: utf-8 -*-
"""The ruler takes its turn in Ctrl+Z / Ctrl+Y (2026-10-25 うにさん「ルーラーの挿入を、Undoの対象にする」).

A ruler toggle is a step of the editor's history like text_format's styles: it is undone while the text and
the tab are as they were when it was made, text edits made after it are undone first, those before it after.
Only hidden Tk windows.
"""
import tkinter as tk
import unittest

from analysis_work import observe_text, _hooks_in_turn
from editor_guides import EditorGuides


class RulerUndoTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = tk.Text(self.root, undo=True, autoseparators=True)
        self.result = tk.Text(self.root)
        observe_text(self.editor)
        self.editor.insert('1.0', '一行目\n二行目\n三行目')
        self.editor.edit_reset()
        self.tab = {'ruler_rows': []}
        self.current = self.tab
        self.saves = []
        self.guides = EditorGuides(self.root, (self.editor, self.result), owner=lambda: self.current,
                                   on_change=lambda: self.saves.append(1))
        self.editor.mark_set('insert', '2.1')

    def tearDown(self):
        self.guides.close()
        self.root.destroy()

    def text(self):
        return self.editor.get('1.0', 'end-1c')

    def undo(self):
        try:                                 # as Tk's <<Undo>> binding: nothing to undo is not an error
            self.editor.edit_undo()
        except tk.TclError:
            pass

    def redo(self):
        try:
            self.editor.edit_redo()
        except tk.TclError:
            pass

    def test_one_undo_removes_the_ruler_and_redo_puts_it_back(self):
        self.assertTrue(self.guides.toggle())
        self.assertEqual(self.guides.ruler_rows(), {2})
        self.undo()
        self.assertEqual(self.guides.ruler_rows(), set())
        self.assertEqual(self.tab['ruler_rows'], [])
        self.assertEqual(self.text(), '一行目\n二行目\n三行目')
        self.redo()
        self.assertEqual(self.guides.ruler_rows(), {2})
        self.assertEqual(self.tab['ruler_rows'], [2])
        self.assertTrue(self.saves)          # the tab's rows are saved as for the button

    def test_removing_a_ruler_is_undone_too(self):
        self.guides.toggle()
        self.guides.toggle()                 # off again
        self.assertEqual(self.guides.ruler_rows(), set())
        self.undo()
        self.assertEqual(self.guides.ruler_rows(), {2})
        self.undo()
        self.assertEqual(self.guides.ruler_rows(), set())

    def test_text_typed_after_the_ruler_is_undone_first(self):
        self.guides.toggle()
        self.editor.edit_separator()
        self.editor.insert('3.end', 'です')
        self.undo()
        self.assertEqual(self.text(), '一行目\n二行目\n三行目')
        self.assertEqual(self.guides.ruler_rows(), {2})
        self.undo()
        self.assertEqual(self.guides.ruler_rows(), set())

    def test_text_typed_before_the_ruler_is_undone_after_it(self):
        self.editor.insert('3.end', 'です')
        self.editor.edit_separator()
        self.guides.toggle()
        self.undo()
        self.assertEqual(self.guides.ruler_rows(), set())
        self.assertEqual(self.text(), '一行目\n二行目\n三行目です')
        self.undo()
        self.assertEqual(self.text(), '一行目\n二行目\n三行目')
        self.redo()
        self.assertEqual(self.text(), '一行目\n二行目\n三行目です')
        self.assertEqual(self.guides.ruler_rows(), set())
        self.redo()
        self.assertEqual(self.guides.ruler_rows(), {2})

    def test_a_new_edit_ends_the_ruler_redo(self):
        self.guides.toggle()
        self.undo()
        self.editor.insert('1.0', 'あ')
        self.redo()
        self.assertEqual(self.guides.ruler_rows(), set())

    def test_another_tab_is_not_touched(self):
        self.guides.toggle()
        other = {'ruler_rows': [3]}
        self.current = other
        self.undo()              # nothing to undo in this tab: Tk's own (empty) history
        self.assertEqual(self.guides.ruler_rows(), {3})
        self.assertEqual(self.tab['ruler_rows'], [2])
        self.current = self.tab
        self.undo()
        self.assertEqual(self.guides.ruler_rows(), set())


class HookTurnTests(unittest.TestCase):
    def test_newest_step_first_for_undo_oldest_first_for_redo(self):
        class Owner:
            def __init__(self, seq):
                self.seq = seq

            def due_step_seq(self, kind):
                return self.seq

            def step(self, kind):
                return True
        old, new = Owner(1), Owner(2)

        def plain(kind):
            return False
        hooks = [old.step, plain, new.step]
        self.assertEqual(_hooks_in_turn(hooks, 'undo'), [new.step, old.step, plain])
        self.assertEqual(_hooks_in_turn(hooks, 'redo'), [old.step, new.step, plain])


if __name__ == '__main__':
    unittest.main()
