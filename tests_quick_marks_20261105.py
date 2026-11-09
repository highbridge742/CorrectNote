# -*- coding: utf-8 -*-
"""The not-yet-analysed bar in the quick pane: only on rows changed since the last answer (2026-11-05). Opens a small window."""
import tkinter as tk
import unittest

import quick_marks as Q
from analysis_work import observe_text


class Rows(unittest.TestCase):
    def test_changed_rows(self):
        self.assertEqual(Q.changed_rows(None, ['a', '', 'b']), {1, 3})
        self.assertEqual(Q.changed_rows(['a', 'b'], ['a', 'b']), set())
        self.assertEqual(Q.changed_rows(['a', 'b', 'c'], ['a', 'x', 'c']), {2})
        self.assertEqual(Q.changed_rows(['a', 'b'], ['a', 'n', 'b']), {2})
        self.assertEqual(Q.changed_rows(['a', 'b', 'c'], ['a', 'c']), set())    # a row taken away leaves nothing to mark
        self.assertEqual(Q.changed_rows(['a'], ['a', '']), set())               # an empty new row has no answer to wait for


class Bars(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('400x200+30+30')
        self.t = tk.Text(self.root, wrap='none', padx=10)
        self.t.pack(fill='both', expand=True)
        self.t.insert('1.0', '一行目\n二行目\n三行目')
        observe_text(self.t)
        self.marks = Q.QuickMarks(self.t, lambda: '#d7c8af')
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def bars(self):
        self.root.update()
        cv = self.marks.canvas
        return [] if cv is None or not self.marks.shown else cv.find_all()

    def test_only_the_changed_row_and_gone_with_the_answer(self):
        self.marks.answered_for(self.t.get('1.0', 'end-1c'))
        self.assertEqual(len(self.bars()), 0)
        self.t.insert('2.end', 'あ')
        self.marks.note_change()
        self.assertEqual(len(self.bars()), 1)
        info = self.t.dlineinfo('2.0')
        top, _left, bottom = None, None, None
        x0, y0, x1, y1 = self.marks.canvas.coords(self.bars()[0])
        self.assertLess(abs(y0 - info[1]), 3)
        self.assertLessEqual(x1 - x0, Q.WIDTH)
        self.marks.answered_for(self.t.get('1.0', 'end-1c'))
        self.assertEqual(len(self.bars()), 0)
        self.assertFalse(self.marks.canvas.winfo_ismapped())

    def test_the_text_is_not_touched(self):
        before = self.t.get('1.0', 'end-1c')
        self.marks.note_change()
        self.root.update()
        self.assertEqual(self.t.get('1.0', 'end-1c'), before)
        self.assertLess(self.marks.canvas.winfo_width(), 10)
        self.assertLessEqual(Q.LEFT + Q.WIDTH, int(self.t.cget('padx')))     # within the left margin, over no letter

    def test_it_follows_a_scroll(self):
        self.t.delete('1.0', 'end')
        self.t.insert('1.0', '\n'.join('行%d' % k for k in range(100)))
        self.marks.answered_for(self.t.get('1.0', 'end-1c'))
        self.t.insert('5.end', 'あ')
        self.marks.note_change()
        self.assertEqual(len(self.bars()), 1)
        self.t.see('90.0')
        self.root.update()
        self.assertEqual(len(self.bars()), 0)     # out of view, nothing drawn
        self.t.see('5.0')
        self.root.update()
        self.assertEqual(len(self.bars()), 1)


class NotOverLetters(unittest.TestCase):
    """2026-11-07 うにさん「未解析の縦線が、文字に被っている」: Text の place は本文の内側（枠＋余白）が 0 だった。"""

    def check(self, font, width, wrap, padx=10, border=1):
        root = tk.Tk()
        try:
            root.geometry('%dx260+30+30' % width)
            t = tk.Text(root, wrap=wrap, padx=padx, pady=8, font=font, borderwidth=border)
            t.pack(fill='both', expand=True)
            t.insert('1.0', 'またあしたの予定を確認します\nCtrlキーを押してから、そこで止まった長い行をもう少し続けて書いてみます\nアプリ')
            observe_text(t)
            marks = Q.QuickMarks(t, lambda: '#d7c8af')
            marks.answered_for('')
            root.update()
            marks.note_change()
            root.update()
            cv = marks.canvas
            self.assertTrue(marks.shown)
            right = cv.winfo_x() + cv.winfo_width()
            checked = []
            for row in (1, 2, 3):
                box = t.bbox('%d.0' % row)
                if box is None:
                    continue        # below the window with a big font: nothing is drawn there
                checked.append(row)
                self.assertLessEqual(right + Q.GAP, box[0], (font, width, wrap, row, right, box))
                # the bar of the row sits beside the row (the same y as the letters)
                info = t.dlineinfo('%d.0' % row)
                bars = [cv.coords(i) for i in cv.find_all()]
                self.assertTrue(any(abs(b[1] + cv.winfo_y() - info[1]) <= 2 for b in bars), (row, bars, info, cv.winfo_y()))
            self.assertTrue(checked)
            self.assertGreaterEqual(cv.winfo_x(), int(t.cget('borderwidth')))      # inside the field, not over its edge
            # wrapped rows: the bar runs down to the last display line of the row
            if wrap != 'none' and t.dlineinfo('2.0') is not None and t.dlineinfo('2.end') is not None:
                last = t.dlineinfo('2.end')
                row2 = [cv.coords(i) for i in cv.find_all() if abs(cv.coords(i)[1] + cv.winfo_y() - t.dlineinfo('2.0')[1]) <= 2]
                self.assertTrue(row2 and row2[0][3] + cv.winfo_y() >= last[1] + last[3] - 3, (row2, last))
        finally:
            root.destroy()

    def test_fonts_widths_and_wrapping(self):
        for font in (('Meiryo', 9), ('Meiryo', 12), ('Meiryo', 20), ('Yu Gothic', 28)):
            for width in (220, 480):
                for wrap in ('none', 'char'):
                    self.check(font, width, wrap)

    def test_a_thicker_border(self):
        self.check(('Meiryo', 12), 220, 'char', border=3)


if __name__ == '__main__':
    unittest.main()
