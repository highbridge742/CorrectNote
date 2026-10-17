# -*- coding: utf-8 -*-
"""Bullet rows from quick input: a blank row before and after every multi-line item.

2026-10-16 うにさん「簡易入力からの箇条書きの行分けが違います。改行がある場合は、
前後に空白行があるようにします。例えば、1行、1行、3行、1行と送って箇条書き行分けした
場合は、3行の前後に空白行を入れます。そのあと最後の1行は、上に空白行が2つありますが、
これは1つでよいです」

Never two blank rows in a row (blank rows already there count). Single-line items
stay one per line. No blank row above at the top of the document, none added at
its end. Colours and one-step undo stay as before.
"""
import tkinter as tk
import unittest
from unittest.mock import Mock
import app


class ListBlankRowsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root = self.root

    def tearDown(self):
        self.root.destroy()

    def editor(self, text, chunks):
        a = self.a
        w = a.editor = tk.Text(self.root, undo=True)
        w.insert('1.0', text)
        w.edit_reset()
        for i, (start, end) in enumerate(chunks):
            w.tag_add('quick_sent_a' if i % 2 == 0 else 'quick_sent_b', start, end)
        a.status = Mock()
        a._flash_editor_header = Mock()
        a._on_change = Mock()
        a.list_mode_btn = object()
        a._refresh_list_button = Mock()
        return w

    def split(self, text, chunks):
        w = self.editor(text, chunks)
        self.assertTrue(self.a._list_from_quick_sent())
        return w, w.get('1.0', 'end-1c')

    def listed(self, w):
        out = []
        for tag in ('quick_listed_a', 'quick_listed_b'):
            r = w.tag_ranges(tag)
            out += [(str(a), w.get(a, b)) for a, b in zip(r[::2], r[1::2])]
        return [t for a, t in sorted(out, key=lambda x: tuple(map(int, x[0].split('.'))))]

    def test_unis_example_one_one_three_one(self):
        sent = '甲乙丙1\n丙2\n丙3丁'
        w, got = self.split(sent, [('1.0', '1.1'), ('1.1', '1.2'), ('1.2', '3.2'), ('3.2', '3.3')])
        self.assertEqual(got, '甲\n乙\n\n丙1\n丙2\n丙3\n\n丁')
        self.assertEqual(self.listed(w), ['甲', '乙', '丙1\n丙2\n丙3', '丁'])
        w.edit_undo()
        self.assertEqual(w.get('1.0', 'end-1c'), sent)

    def test_multi_line_first_item(self):
        # At the top of the document: no blank row above.
        _, got = self.split('丙1\n丙2甲乙', [('1.0', '2.2'), ('2.2', '2.3'), ('2.3', '2.4')])
        self.assertEqual(got, '丙1\n丙2\n\n甲\n乙')
        # Text right above: one blank row above.
        _, got = self.split('前の行\n丙1\n丙2甲', [('2.0', '3.2'), ('3.2', '3.3')])
        self.assertEqual(got, '前の行\n\n丙1\n丙2\n\n甲')
        # A blank row already above: nothing more.
        _, got = self.split('前の行\n\n丙1\n丙2甲', [('3.0', '4.2'), ('4.2', '4.3')])
        self.assertEqual(got, '前の行\n\n丙1\n丙2\n\n甲')

    def test_multi_line_last_item(self):
        # The end of the document: none added below.
        _, got = self.split('甲丙1\n丙2', [('1.0', '1.1'), ('1.1', '2.2')])
        self.assertEqual(got, '甲\n\n丙1\n丙2')
        # Text right below: one blank row.
        _, got = self.split('甲丙1\n丙2\n次', [('1.0', '1.1'), ('1.1', '2.2')])
        self.assertEqual(got, '甲\n\n丙1\n丙2\n\n次')
        # Already a blank row below: nothing more.
        _, got = self.split('甲丙1\n丙2\n\n次', [('1.0', '1.1'), ('1.1', '2.2')])
        self.assertEqual(got, '甲\n\n丙1\n丙2\n\n次')

    def test_two_multi_line_items_in_a_row(self):
        _, got = self.split('甲丙1\n丙2\n丙3丁1\n丁2戊',
                            [('1.0', '1.1'), ('1.1', '3.2'), ('3.2', '4.2'), ('4.2', '4.3')])
        self.assertEqual(got, '甲\n\n丙1\n丙2\n丙3\n\n丁1\n丁2\n\n戊')

    def test_an_item_already_ending_its_line_gets_no_second_blank(self):
        # The three-line item was sent with its own line break at the end.
        _, got = self.split('甲乙丙1\n丙2\n丙3\n丁', [('1.0', '1.1'), ('1.1', '1.2'), ('1.2', '4.0'), ('4.0', '4.1')])
        self.assertEqual(got, '甲\n乙\n\n丙1\n丙2\n丙3\n\n丁')

    def test_never_two_blank_rows_anywhere(self):
        cases = [
            ('甲乙丙1\n丙2\n丙3丁', [('1.0', '1.1'), ('1.1', '1.2'), ('1.2', '3.2'), ('3.2', '3.3')]),
            ('前\n丙1\n丙2丁1\n丁2\n次', [('2.0', '3.2'), ('3.2', '4.2')]),
            ('甲丙1\n丙2\n\n次', [('1.0', '1.1'), ('1.1', '2.2')]),
        ]
        for text, chunks in cases:
            with self.subTest(text=text):
                _, got = self.split(text, chunks)
                self.assertNotIn('\n\n\n', got)

    def test_moved_items_from_mid_sentence(self):
        w = self.editor('前甲乙丙1\n丙2\n丙3丁後', [('1.1', '1.2'), ('1.2', '1.3'), ('1.3', '3.2'), ('3.2', '3.3')])
        w.mark_set('insert', '3.end')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲\n乙\n\n丙1\n丙2\n丙3\n\n丁')
        self.assertEqual(self.listed(w), ['甲', '乙', '丙1\n丙2\n丙3', '丁'])
        w.edit_undo()
        self.assertEqual(w.get('1.0', 'end-1c'), '前甲乙丙1\n丙2\n丙3丁後')

    def test_single_line_items_unchanged(self):
        _, got = self.split('甲乙丙後\n次', [('1.0', '1.1'), ('1.1', '1.2'), ('1.2', '1.3')])
        self.assertEqual(got, '甲\n乙\n丙後\n\n次')


if __name__ == '__main__':
    unittest.main()
