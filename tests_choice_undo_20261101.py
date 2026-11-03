# -*- coding: utf-8 -*-
"""補正欄の選び直しを Ctrl+Z / Ctrl+Y の履歴に入れる（choice_undo・2026-11-01 うにさん）。本文は書き換えない。
本文の編集と交互に戻る（あとの本文の編集を先に戻し、そのあとで選び直しを戻す）。"""
import os
import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace

import choice_undo
import last_choice


class ChoiceUndoTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.text = tk.Text(self.root, undo=True)
        self.text.pack()
        self.folder = tempfile.TemporaryDirectory()
        self.choices = last_choice.LastChoiceStore(os.path.join(self.folder.name, 'last_choice.json'))
        self.rendered = []
        self.app = SimpleNamespace(editor=self.text, choices=self.choices, status=SimpleNamespace(config=lambda **kw: None),
                                   _render_corrected=lambda: self.rendered.append(self.choices.lookup('資料', 'の', 'を')))
        self.undo = choice_undo.install(self.app)
        self.text.insert('1.0', '会議の資料を作成')
        self.text.edit_separator()

    def tearDown(self):
        self.root.destroy()
        self.folder.cleanup()

    def _choose(self):
        before = self.undo.before()
        self.choices.record('資料', '史料', 'しりょう', 'の', 'を')
        return self.undo.after(before)

    def test_undo_and_redo_a_choice_without_touching_the_text(self):
        self.assertTrue(self._choose())
        self.text.edit_undo()
        self.assertIsNone(self.choices.lookup('資料', 'の', 'を'))
        self.assertEqual(self.text.get('1.0', 'end-1c'), '会議の資料を作成')
        self.text.edit_redo()
        self.assertEqual(self.choices.lookup('資料', 'の', 'を'), '史料')
        self.assertEqual(self.rendered[-2:], [None, '史料'])

    def test_a_later_text_edit_is_undone_first(self):
        self._choose()
        self.text.insert('end', 'した')
        self.text.edit_separator()
        self.text.edit_undo()                      # 本文の編集
        self.assertEqual(self.text.get('1.0', 'end-1c'), '会議の資料を作成')
        self.assertEqual(self.choices.lookup('資料', 'の', 'を'), '史料')
        self.text.edit_undo()                      # 選び直し
        self.assertIsNone(self.choices.lookup('資料', 'の', 'を'))

    def test_undo_draws_the_underline_where_the_choice_was(self):
        # 戻したとき・やり直したとき、補正欄の語と本文の語に Undo の下線（2026-11-01）
        drawn = []
        with __import__('unittest.mock', fromlist=['patch']).patch.object(
                choice_undo, 'mark', lambda app, row, start, source, shown, redo=False: drawn.append((row, source, shown, redo))):
            before = self.undo.before()
            self.choices.record('資料', '史料', 'しりょう', 'の', 'を')
            self.undo.after(before, (1, 3, '資料', '資料', '史料'))
            self.text.edit_undo()
            self.text.edit_redo()
        self.assertEqual(drawn, [(1, '資料', '資料', False), (1, '資料', '史料', True)])

    def test_nothing_changed_is_not_a_step(self):
        self._choose()
        before = self.undo.before()
        self.assertFalse(self.undo.after(before))
        self.assertEqual(len(self.undo.history), 1)


if __name__ == '__main__':
    unittest.main()
