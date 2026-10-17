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

    def test_two_line_breaks_after_a_sized_row_keep_row_one_whole(self):
        # 2026-10-14 うにさん「簡易入力で2回改行したら、1行目の上半分が見切れている」:
        # the height was counted in base-font lines, but a row with POS-sized
        # characters is taller, so three rows overflowed and Tk scrolled row 1 up.
        a = self.a
        win = tk.Toplevel(self.root); win.geometry('+60+60')
        w = tk.Text(win, font=('TkFixedFont', 10), padx=10, pady=8,
                    height=a.QUICK_MIN_LINES, width=a.QUICK_MIN_WIDTH, wrap='none')
        w.pack(fill='both', expand=True)
        a._quick_win = win
        a._editor_font = lambda: ('TkFixedFont', 10)
        w.insert('1.0', '資料を確認する')
        w.tag_configure('pos_font_0', font=('TkFixedFont', 20))
        w.tag_add('pos_font_0', '1.0', '1.2')
        win.update()
        a._adjust_quick_size(w)
        for _ in range(2):
            w.insert('insert', '\n'); w.see('insert')
            a._adjust_quick_size(w); win.update()
        self.assertEqual(w.yview()[0], 0.0)
        box = w.bbox('1.0')
        self.assertIsNotNone(box)
        self.assertGreaterEqual(box[1], 0)
        # The last row (with the cursor) is visible too.
        self.assertIsNotNone(w.bbox('3.0'))
        win.destroy()

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
        # (the row after the list has text: one blank row before it, 2026-10-15)
        self.assertEqual(w.get('1.0', 'end-1c'), '甲1\n甲2\n\n乙\n丙\n\n次')
        w.edit_undo();self.assertEqual(w.get('1.0', 'end-1c'), '甲1\n甲2乙丙\n次')
        # Single-line items stay one per line, as before.
        w = self.editor('甲乙丙後\n次', [('1.0', '1.1'), ('1.1', '1.2'), ('1.2', '1.3')])
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '甲\n乙\n丙後\n\n次')
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

    def test_a_blank_row_parts_the_list_from_the_text_below(self):
        # 2026-10-15 うにさん「簡易入力を送ってから箇条書きボタンで新しい行に送った
        # 文字が、その次の行に別の文字があったら、間に空白行を1行挿入し、別の文字と
        # 間隔を開ける」
        w = self.editor('甲乙\n次の段落', [('1.0', '1.1'), ('1.1', '1.2')])
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '甲\n乙\n\n次の段落')
        self.assertEqual(w.get('insert linestart', 'insert'), '乙')   # the cursor stays on the list
        w.edit_undo();self.assertEqual(w.get('1.0', 'end-1c'), '甲乙\n次の段落')   # one step
        # Already a blank (or whitespace-only) row: nothing more.
        for below in ('\n\n次', '\n  \n次', '\n\t\n次'):
            w = self.editor('甲乙' + below, [('1.0', '1.1'), ('1.1', '1.2')])
            self.a._list_from_quick_sent()
            self.assertEqual(w.get('1.0', 'end-1c'), '甲\n乙' + below)
        # The end of the document: nothing added.
        w = self.editor('甲乙', [('1.0', '1.1'), ('1.1', '1.2')])
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '甲\n乙')
        # A multi-line last item: one blank row above it (2026-10-16) and one below only
        # (no double with the 2026-10-13 rule).
        w = self.editor('甲乙1\n乙2\n次', [('1.0', '1.1'), ('1.1', '2.2')])
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '甲\n\n乙1\n乙2\n\n次')

    def test_moved_items_get_the_same_blank_row_before_the_text_below(self):
        w = self.editor('前甲乙後\n次の段落', [('1.1', '1.2'), ('1.2', '1.3')])
        w.mark_set('insert', '1.0')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲\n乙\n\n次の段落')
        self.assertEqual(w.get('insert linestart', 'insert'), '乙')
        self.assertEqual(self.ranges(w, 'quick_listed_a'), ['甲'])
        self.assertEqual(self.ranges(w, 'quick_listed_b'), ['乙'])
        w.edit_undo();self.assertEqual(w.get('1.0', 'end-1c'), '前甲乙後\n次の段落')
        w = self.editor('前甲乙後\n\n次', [('1.1', '1.2'), ('1.2', '1.3')])
        w.mark_set('insert', '1.0')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲\n乙\n\n次')

    def ranges(self, w, tag):
        r = w.tag_ranges(tag)
        return [w.get(a, b) for a, b in zip(r[::2], r[1::2])]

    def test_split_rows_keep_the_sent_colours(self):
        # 2026-10-14 うにさん「箇条書きで行を分けた時点では、まだ一時的な
        # 背景色を残しておく」。Each row keeps its own colour until typing.
        w = self.editor('甲1\n甲2乙丙\n次', [('1.0', '2.2'), ('2.2', '2.3'), ('2.3', '2.4')])
        self.a._list_from_quick_sent()
        self.assertEqual(self.ranges(w, 'quick_listed_a'), ['甲1\n甲2', '丙'])
        self.assertEqual(self.ranges(w, 'quick_listed_b'), ['乙'])
        # The colours are set here too: startup need not pass _apply_theme
        # (seen on the real app: the rows lost their colour without this).
        import app as A
        self.assertEqual(w.tag_cget('quick_listed_a', 'background'), A.QUICK_SENT_BG_A)
        self.assertEqual(w.tag_cget('quick_listed_b', 'background'), A.QUICK_SENT_BG_B)
        # The planner sees nothing left to split; the inserted breaks are uncoloured.
        self.assertEqual(self.ranges(w, 'quick_sent_a') + self.ranges(w, 'quick_sent_b'), [])
        self.assertEqual(self.a._list_quick_sent_plan(), (None, []))
        self.a._clear_quick_sent()
        self.assertEqual(self.ranges(w, 'quick_listed_a') + self.ranges(w, 'quick_listed_b'), [])

    def test_moved_rows_keep_the_sent_colours(self):
        w = self.editor('前甲1\n甲2乙後', [('1.1', '2.2'), ('2.2', '2.3')])
        w.mark_set('insert', '2.end')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲1\n甲2\n\n乙')
        self.assertEqual(self.ranges(w, 'quick_listed_a'), ['甲1\n甲2'])
        self.assertEqual(self.ranges(w, 'quick_listed_b'), ['乙'])
        self.assertEqual(self.a._list_quick_sent_plan(), (None, []))
        # Undo restores the text in one step, as before.
        w.edit_undo();self.assertEqual(w.get('1.0', 'end-1c'), '前甲1\n甲2乙後')

    def test_a_new_send_after_listing_is_planned_alone(self):
        w = self.editor('前甲乙後', [('1.1', '1.2'), ('1.2', '1.3')])
        w.mark_set('insert', '1.0')
        self.a._list_from_quick_sent()
        self.assertEqual(w.get('1.0', 'end-1c'), '前後\n\n甲\n乙')
        # A later send mid-sentence moves on its own; the kept rows stay put.
        w.insert('1.1', '丙');w.tag_add('quick_sent_a', '1.1', '1.2')
        w.mark_set('insert', '1.0')
        mode, chunks = self.a._list_quick_sent_plan()
        self.assertEqual((mode, [c[3] for c in chunks]), ('move', ['丙']))


if __name__ == '__main__':
    unittest.main()
