# -*- coding: utf-8 -*-
"""Showing the picture through the text pane, in a real window. Opens a window: run only when one may be shown.
Made-up text. The mouse messages are posted to the windows; the real mouse does not move."""
import ctypes
import ctypes.wintypes as wt
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path

import appearance as ap
import paper_window as pw

BG = '#f0f0ed'
user32 = ctypes.WinDLL('user32')
user32.PostMessageW.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int)
LBUTTONDOWN, LBUTTONUP, RBUTTONDOWN, RBUTTONUP, WHEEL, MOVE = 0x201, 0x202, 0x204, 0x205, 0x20A, 0x200


@unittest.skipUnless(pw.available(), 'no child layered windows here')
class Through(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ap.Paper.SHOW_THROUGH = True
        cls.root = tk.Tk()
        cls.root.geometry('640x420+50+50')
        cls.frame = tk.Frame(cls.root)
        cls.frame.pack(fill='both', expand=True)
        cls.t = tk.Text(cls.frame, bg=BG, wrap='char', bd=0, highlightthickness=0, padx=8)
        cls.t.pack(fill='both', expand=True)
        cls.t.insert('1.0', chr(10).join('%d 行目の作り物の文です。' % k for k in range(1, 400)))
        cls.observers = cls.t._correctnote_observers = {}
        cls.paper = ap.Paper(cls.t)
        cls.pump(cls, .1)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def pump(self, s=.15):
        end = time.monotonic() + s
        while time.monotonic() < end:
            self.root.update()
            time.sleep(.005)

    def setUp(self):
        self.paper.set('nami', '#d0d0cc', BG)
        self.pump()
        self.assertTrue(self.paper._through)

    def hwnds(self):
        return int(self.paper._back.winfo_id()), int(self.t.winfo_id())

    def test_the_back_is_right_under_the_text_and_nothing_is_pasted(self):
        back, text = self.hwnds()
        self.assertTrue(user32.GetWindowLongPtrW(text, -20) & pw.WS_EX_LAYERED)
        self.assertFalse(user32.GetWindowLongPtrW(back, -16) & pw.WS_CLIPSIBLINGS)
        self.assertEqual((self.paper._back.winfo_rootx(), self.paper._back.winfo_rooty()), (self.t.winfo_rootx(), self.t.winfo_rooty()))
        self.assertEqual((self.paper._back.winfo_width(), self.paper._back.winfo_height()), (self.t.winfo_width(), self.t.winfo_height()))
        self.assertEqual(self.paper._slots, [])
        self.assertFalse([n for n in self.t.tag_names() if n.startswith(ap.PAPER_PREFIX)])
        self.assertEqual(self.paper._back.find_withtag('art') != (), True)

    def test_scrolling_changes_nothing(self):
        key = self.paper._back_key
        coords = self.paper._back.coords('art')
        self.t.yview_scroll(40, 'pixels')
        self.pump()
        self.assertEqual(self.paper._back_key, key)
        self.assertEqual(self.paper._back.coords('art'), coords)
        self.assertFalse([n for n in self.t.tag_names() if n.startswith(ap.PAPER_PREFIX)])

    def test_mouse_messages_on_the_back_go_to_the_text(self):
        # Tk takes a press from the real button state, so a posted one makes no event: the arrival of the message is what is seen here
        back, text = self.hwnds()
        comctl = ctypes.WinDLL('comctl32')
        Proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_size_t)
        comctl.SetWindowSubclass.argtypes = (wt.HWND, Proc, ctypes.c_size_t, ctypes.c_size_t)
        comctl.RemoveWindowSubclass.argtypes = (wt.HWND, Proc, ctypes.c_size_t)
        comctl.DefSubclassProc.restype = ctypes.c_ssize_t
        comctl.DefSubclassProc.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        seen = []
        def record(hwnd, msg, wparam, lparam, uid, ref):
            if msg in pw.MOUSE_MESSAGES:
                seen.append((msg, wparam, lparam))
                return 0
            return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)
        proc = Proc(record)
        self.assertTrue(comctl.SetWindowSubclass(text, proc, 77, 0))
        try:
            xy = 120 | (40 << 16)
            sent = [(MOVE, 0, xy), (LBUTTONDOWN, 1, xy), (LBUTTONUP, 0, xy), (RBUTTONDOWN, 2, xy), (RBUTTONUP, 0, xy), (WHEEL, 120 << 16, xy)]
            for message in sent:
                user32.PostMessageW(back, *message)
            self.pump(.2)
            self.assertEqual([m for m in seen if m in sent], sent)
        finally:
            comctl.RemoveWindowSubclass(text, proc, 77)

    def test_a_new_colour_moves_the_key(self):
        try:
            self.t.configure(bg='#202024')
            self.paper.set('nami', '#303038', '#202024')
            self.pump()
            self.assertEqual(self.paper._through_key, pw.colorref(self.t.winfo_rgb('#202024')))
            self.assertEqual(str(self.paper._back.cget('bg')), '#202024')
        finally:
            self.t.configure(bg=BG)

    def test_no_decoration_is_an_ordinary_pane(self):
        _back, text = self.hwnds()
        self.paper.set('none', '#d0d0cc', BG)
        self.pump()
        self.assertFalse(self.paper._through)
        self.assertIsNone(self.paper._back)
        self.assertFalse(user32.GetWindowLongPtrW(text, -20) & pw.WS_EX_LAYERED)

    def test_the_picture_stays_with_a_new_size(self):
        coords = self.paper._back.coords('art')
        self.root.geometry('760x500')
        self.pump(.5)
        self.assertEqual((self.paper._back.winfo_width(), self.paper._back.winfo_height()), (self.t.winfo_width(), self.t.winfo_height()))
        self.assertNotEqual(self.paper._back.coords('art'), coords)      # the corner it is held to has moved
        self.root.geometry('640x420')
        self.pump(.5)


if __name__ == '__main__':
    unittest.main()
