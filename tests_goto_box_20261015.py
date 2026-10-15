# -*- coding: utf-8 -*-
"""Ctrl+G の「行へ移る・文字を探す」欄（goto_box.py・2026-10-15 うにさん）。"""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import goto_box


class ParseTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(goto_box.parse_line('12'), 12)
        self.assertEqual(goto_box.parse_line('１２'), 12)       # 全角
        self.assertEqual(goto_box.parse_line('  7 '), 7)
        self.assertEqual(goto_box.parse_line('0'), 0)
        for text in ('12a', '一二', '1.5', '-3', '٣', ''):
            self.assertIsNone(goto_box.parse_line(text), text)


class GotoBoxTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('500x300+40+40')
        self.editor = tk.Text(self.root, undo=True, height=8)
        self.editor.pack(fill='both', expand=True)
        self.result = tk.Text(self.root, height=3)
        self.result.pack()
        lines = ['%d 行目 Apple' % i if i % 10 == 0 else '%d 行目' % i for i in range(1, 61)]
        self.editor.insert('1.0', '\n'.join(lines))
        self.editor.edit_reset()
        self.moves = []

        def goto(line, centered=True):
            self.moves.append((line, centered))
            self.editor.mark_set('insert', f'{line}.0')
        self.app = SimpleNamespace(root=self.root, editor=self.editor, result_view=self.result,
                                   status=Mock(), _goto_line=goto)
        self.box = goto_box.GotoBox(self.app)
        self.root.update()
        self.editor.focus_force()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def run_box(self, text):
        self.assertEqual(self.box.open(), 'break')
        self.assertIsNotNone(self.box.entry)
        self.box.var.set(text)
        self.box._enter()
        self.assertIsNone(self.box.frame)

    def line_col(self):
        row, col = self.editor.index('insert').split('.')
        return int(row), self.editor.get(f'{row}.0', 'insert')

    def test_a_number_goes_to_that_line(self):
        self.run_box('25')
        self.assertEqual(self.moves, [(25, True)])
        self.assertEqual(self.line_col(), (25, ''))

    def test_out_of_range_and_zero_and_fullwidth(self):
        self.run_box('999')
        self.run_box('0')
        self.run_box('　３２　')
        self.assertEqual(self.moves, [(60, True), (1, True), (32, True)])

    def test_text_is_found_below_the_cursor_and_the_cursor_goes_to_its_end(self):
        self.editor.mark_set('insert', '12.0')
        self.run_box('apple')          # 大文字小文字は区別しない
        self.assertEqual(self.line_col(), (20, '20 行目 Apple'))
        # 2回目は前の入力が全部選ばれて出る。そのまま Enter で次の該当へ
        self.box.open()
        self.assertEqual(self.box.var.get(), 'apple')
        self.assertTrue(self.box.entry.selection_present())
        self.box._enter()
        self.assertEqual(self.line_col(), (30, '30 行目 Apple'))

    def test_wraps_to_the_top_when_nothing_is_below(self):
        self.editor.mark_set('insert', '60.end')
        self.run_box('Apple')
        self.assertEqual(self.line_col(), (10, '10 行目 Apple'))

    def test_not_found_says_so_below_and_does_not_move(self):
        self.editor.mark_set('insert', '5.2')
        before = self.editor.index('insert')
        self.run_box('Banana')
        self.assertEqual(self.editor.index('insert'), before)
        self.app.status.config.assert_called_with(text='「Banana」は見つかりません')
        self.assertEqual([w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)], [])

    def test_empty_does_nothing(self):
        self.editor.mark_set('insert', '5.2')
        self.run_box('   ')
        self.assertEqual(self.editor.index('insert'), '5.2')
        self.assertEqual(self.moves, [])
        self.app.status.config.assert_not_called()

    def test_escape_closes_without_moving(self):
        self.editor.mark_set('insert', '5.2')
        self.box.open()
        self.box.var.set('40')
        self.box.entry.focus_force()
        self.root.update()
        self.box.entry.event_generate('<Escape>')
        self.root.update()
        self.assertIsNone(self.box.frame)
        self.assertEqual(self.editor.index('insert'), '5.2')

    def test_the_end_of_an_emoji_cluster(self):
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', 'あ👍🏽い❤️う\n次')
        self.editor.mark_set('insert', '1.0')
        self.run_box('👍')                # 肌の色の前で止めない
        self.assertEqual(self.line_col(), (1, 'あ👍🏽'))
        self.editor.mark_set('insert', '1.0')
        self.run_box('❤')                 # FE0F の前で止めない
        self.assertEqual(self.line_col(), (1, 'あ👍🏽い❤️'))
        self.run_box('う')                 # 絵文字の後ろの字も正しい場所
        self.assertEqual(self.line_col(), (1, 'あ👍🏽い❤️う'))

    def test_the_undo_history_does_not_grow(self):
        self.run_box('30')
        self.run_box('Apple')
        with self.assertRaises(tk.TclError):
            self.editor.edit_undo()        # 何も戻すものが無い

    def test_the_correction_pane_is_the_target_when_it_has_the_focus(self):
        self.result.insert('1.0', 'x\ny\nz')
        self.result.focus_force()
        self.root.update()
        self.run_box('3')
        self.assertEqual(self.result.index('insert'), '3.0')
        self.assertIs(self.root.focus_get(), self.result)

    def test_only_while_the_main_window_has_the_focus(self):
        other = tk.Toplevel(self.root)
        e = tk.Entry(other)
        e.pack()
        e.focus_force()
        self.root.update()
        if self.root.focus_get() is e:
            self.assertIsNone(self.box.open())
            self.assertIsNone(self.box.frame)

    def test_installed_on_the_main_window_only(self):
        app = SimpleNamespace(root=self.root, editor=self.editor, result_view=self.result,
                              status=Mock(), _goto_line=lambda *a, **k: None)
        goto_box.install(app)
        self.editor.focus_force()
        self.root.update()
        self.editor.event_generate('<Control-g>')
        self.root.update()
        self.assertIsNotNone(app._goto_box.frame)
        self.assertIs(self.root.focus_get(), app._goto_box.entry)
        app._goto_box.close()
        other = tk.Toplevel(self.root)
        t = tk.Text(other)
        t.pack()
        t.focus_force()
        self.root.update()
        t.event_generate('<Control-g>')
        self.root.update()
        self.assertIsNone(app._goto_box.frame)


if __name__ == '__main__':
    unittest.main()
