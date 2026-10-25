# -*- coding: utf-8 -*-
"""Quick Input and the word book called one after the other do not cover each other (2026-10-23
うにさん「簡易入力と単語帳の窓を続けて呼ぶと重なる。あとから呼んだ方の位置をずらす」). The one
called later goes beside the pointer where the other is not, inside the pointer's monitor; if
nowhere is free, where it overlaps least. Windows are transparent and far off the screens."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, window_place

AREA = (10000, 0, 11920, 1040)          # a monitor right of the others (no real screen there)


def overlap(a, b):
    return window_place._overlap(a, b)


class PlacementTests(unittest.TestCase):
    def test_below_right_when_nothing_is_in_the_way(self):
        self.assertEqual(window_place.near_pointer((10500, 300), (300, 200), AREA), (10516, 316))
        # At the edges: moved up or left inside the monitor
        self.assertEqual(window_place.near_pointer((11900, 1030), (300, 200), AREA), (11612, 832))

    def test_another_place_when_the_other_window_is_there(self):
        other = (10510, 310, 10900, 700)                      # Quick Input below right of the pointer
        x, y = window_place.near_pointer((10500, 300), (300, 200), AREA, avoid=(other,))
        self.assertEqual(overlap((x, y, x + 300, y + 200), other), 0)
        self.assertEqual((x, y), (10184, 316))               # below left of the pointer

    def test_inside_the_monitor_and_least_overlap_when_nothing_is_free(self):
        other = (10050, 50, 11850, 1000)                      # covers almost the whole monitor
        x, y = window_place.near_pointer((10500, 300), (300, 200), AREA, avoid=(other,))
        self.assertTrue(AREA[0] <= x and x + 300 <= AREA[2] and AREA[1] <= y and y + 200 <= AREA[3])
        best = min(overlap((cx, cy, cx + 300, cy + 200), other)
                   for cx in range(AREA[0], AREA[2] - 300, 10) for cy in range(AREA[1], AREA[3] - 200, 10))
        self.assertLessEqual(overlap((x, y, x + 300, y + 200), other), best + 300 * 10)


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.attributes('-alpha', 0); self.root.geometry('200x100+10000+900')
        self.root.update()

    def tearDown(self):
        self.root.update()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def window(self, geometry):
        win = tk.Toplevel(self.root); win.attributes('-alpha', 0)
        win.geometry(geometry); win.update()
        return win

    def test_quick_input_does_not_cover_the_word_book(self):
        book = self.window('300x400+10516+316')                # the word book, below right of the pointer
        quick = self.window('260x80+10000+0')
        quick.winfo_pointerxy = lambda: (10500, 300)
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root; a._word_book = SimpleNamespace(window=book)
        with patch.object(app, 'monitor_work_area', return_value=AREA):
            a._place_quick_window(quick)
        quick.update()
        self.assertEqual(overlap(window_place.outer_rect(quick), window_place.outer_rect(book)), 0)
        # Without the word book: below right as before
        book.withdraw()
        with patch.object(app, 'monitor_work_area', return_value=AREA):
            a._place_quick_window(quick)
        quick.update()
        self.assertEqual((quick.winfo_x(), quick.winfo_y()), (10516, 316))

    def test_word_book_does_not_cover_quick_input(self):
        import word_book
        quick = self.window('260x80+10516+316')                # Quick Input, below right of the pointer
        win = self.window('186x200+10000+0')
        win.winfo_pointerxy = lambda: (10500, 300)
        book = word_book.WordBook.__new__(word_book.WordBook)
        book.app = SimpleNamespace(root=self.root, _quick_win=quick)
        book.window = win; book.work_area = lambda x, y: AREA; book._drag_anchor = None
        book._place(near_pointer=True)
        end = time.monotonic() + .5
        while time.monotonic() < end:
            self.root.update(); time.sleep(.01)
        self.assertEqual(overlap(window_place.outer_rect(win), window_place.outer_rect(quick)), 0)


if __name__ == '__main__':
    unittest.main()
