# -*- coding: utf-8 -*-
"""Quick input: the window fits sized characters; list moves keep multi-line items apart."""
import tkinter as tk
import tkinter.font as tkfont
import unittest
from unittest.mock import Mock
import app


class QuickInputLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk();self.root.withdraw()
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root = self.root

    def tearDown(self):
        self.root.destroy()

    def test_rows_are_measured_with_the_fonts_their_tags_give(self):
        # 2026-10-13 うにさん：品詞ごとのサイズの字があると、窓が広がりきらず見切れた
        w = tk.Text(self.root, font=('TkFixedFont', 10))
        base = tkfont.Font(font=w.cget('font'))
        w.insert('1.0', '資料を確認する\n短い')
        big = ('TkFixedFont', 20)
        w.tag_configure('pos_font_0', font=big)
        w.tag_configure('fmt_bold', font=('TkFixedFont', 10, 'bold'))
        w.tag_add('pos_font_0', '1.0', '1.2')
        w.tag_add('fmt_bold', '1.1', '1.3')       # Later tag wins on 1.1.
        line = w.get('1.0', '1.end')
        expected = (tkfont.Font(font=big).measure('資')
                    + tkfont.Font(font=('TkFixedFont', 10, 'bold')).measure('料を')
                    + base.measure('確認する'))
        self.assertEqual(self.a._quick_line_px(w, 1, line, base), max(expected, base.measure(line)))
        self.assertGreater(self.a._quick_line_px(w, 1, line, base), base.measure(line))
        # A row without sized characters is the plain measure.
        self.assertEqual(self.a._quick_line_px(w, 2, '短い', base), base.measure('短い'))
        # A tag reaching across rows counts only this row's part.
        w.tag_add('pos_font_0', '1.5', '2.1')
        self.assertEqual(self.a._quick_line_px(w, 2, '短い', base),
                         max(base.measure('短い'),
                             tkfont.Font(font=big).measure('短') + base.measure('い')))

    def editor(self, text, chunks):
        a = self.a
        w = a.editor = tk.Text(self.root, undo=True)
        w.insert('1.0', text);w.edit_reset()
        for i, (start, end) in enumerate(chunks):
            w.tag_add('quick_sent_a' if i % 2 == 0 else 'quick_sent_b', start, end)
        a.status = Mock();a._flash_editor_header = Mock();a._on_change = Mock()
        a.list_mode_btn = object();a._refresh_list_button = Mock()
        return w

    def test_a_blank_row_follows_a_quick_input_with_a_line_break(self):
        # 2026-10-13 うにさん：改行が入っている簡易入力のあとには空白行をひとつ挟む
        w = self.editor('甲1\n甲2乙丙\n次', [('1.0', '2.2'), ('2.2', '2.3'), ('2.3', '2.4')])
        self.assertTrue(self.a._list_from_quick_sent())
        self.assertEqual(w.get('1.0', 'end-1c'), '甲1\n甲2\n\n乙\n丙\n次')
        w.edit_undo();self.assertEqual(w.get('1.0', 'end-1c'), '甲1\n甲2乙丙\n次')
        # Single-line items stay one per line, as before.
        w = self.editor('甲乙丙後\n次', [('1.0', '1.1'), ('1.1', '1.2'), ('1.2', '1.3')])
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '甲\n乙\n丙後\n次')
        # An item that already ends its line still gets the blank row.
        w = self.editor('甲1\n甲2\n乙', [('1.0', '3.0'), ('3.0', '3.1')])
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '甲1\n甲2\n\n乙')

    def test_moved_items_from_mid_sentence_keep_the_same_rule(self):
        w = self.editor('前甲1\n甲2乙後', [('1.1', '2.2'), ('2.2', '2.3')])
        w.mark_set('insert', '2.end')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲1\n甲2\n\n乙')
        w = self.editor('前甲乙後', [('1.1', '1.2'), ('1.2', '1.3')])
        w.mark_set('insert', '1.0')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲\n乙')


if __name__ == '__main__':
    unittest.main()
