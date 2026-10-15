# -*- coding: utf-8 -*-
"""Centring margins after a bookmark jump stay in the pane's own colour.

2026-10-14 うにさん「1行目に紫の背景色が付いて、1行目にブックマーク移動すると、
上の端から中央まで背景色が伸びてしまう」: Tk paints a tag's background over
the whole line height, so the margin above row 1 (spacing1) took the row's
purple. Plain strips in the pane's colour cover only the empty margin."""
import unittest
import tkinter as tk
import app


class NavigationMarginTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.geometry('400x300+40+40')
        self.w = tk.Text(self.root, bg='#f0f0ed', font=('Meiryo', 11)); self.w.pack(fill='both', expand=True)
        self.w.insert('1.0', '紫の行です。\n二行目\n三行目')
        self.w.tag_configure('odd', background='#e6cbf3'); self.w.tag_add('odd', '1.0', '1.3')
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.root.update()

    def tearDown(self):
        self.a = None; self.w = None
        self.root.destroy()

    def test_strips_cover_only_the_margins_and_go_with_them(self):
        w = self.w
        w.tag_configure('navigation_head', spacing1=120); w.tag_add('navigation_head', '1.0', '1.0+1c')
        w.tag_configure('navigation_tail', spacing3=80); w.tag_add('navigation_tail', 'end-2c linestart', 'end')
        self.root.update()
        self.a._mask_navigation_margins(w); self.root.update()
        masks = w._correctnote_navigation_masks
        self.assertEqual(len(masks), 2)
        head, tail = masks
        first, last = w.bbox('1.0'), w.bbox('end-1c')
        # Above row 1 up to its characters; below the last row from its characters.
        self.assertEqual(head.winfo_y() + head.winfo_height(), first[1])
        self.assertEqual(tail.winfo_y(), last[1] + last[3])
        for mask in masks:
            self.assertEqual(mask.cget('bg'), '#f0f0ed')
        # The purple row itself stays visible: nothing covers its characters.
        for row in ('1.0', '2.0', '3.0'):
            box = w.bbox(row)
            for mask in masks:
                self.assertFalse(mask.winfo_y() < box[1] + box[3] and box[1] < mask.winfo_y() + mask.winfo_height(), row)
        self.a._unmask_navigation_margins(w)
        self.assertEqual(w._correctnote_navigation_masks, [])
        self.assertFalse([c for c in w.winfo_children() if isinstance(c, tk.Frame)])

    def test_no_margin_no_strip(self):
        self.a._mask_navigation_margins(self.w)
        self.assertEqual(self.w._correctnote_navigation_masks, [])


if __name__ == '__main__':
    unittest.main()
