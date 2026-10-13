# -*- coding: utf-8 -*-
"""The word book opens wide enough that its title bar icon clears the buttons."""
import ctypes
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as N
from unittest.mock import patch
import word_book


class _RECT(ctypes.Structure):
    _fields_ = [(name, ctypes.c_long) for name in ('left', 'top', 'right', 'bottom')]


class CaptionWidthTests(unittest.TestCase):
    def native(self, failed=0, left=10, right=148):
        def attribute(hwnd, attr, pointer, size):
            self.assertEqual(attr, 5)          # DWMWA_CAPTION_BUTTON_BOUNDS
            pointer._obj.left, pointer._obj.right = left, right
            return failed
        libraries = dict(dwmapi=N(DwmGetWindowAttribute=attribute),
                         user32=N(GetSystemMetrics=lambda index: 16,
                                  GetAncestor=lambda hwnd, flag: 77))
        stack = ExitStack()
        stack.enter_context(patch('ctypes.WinDLL', lambda name: libraries[name], create=True))
        # Windows' ctypes.wintypes does not import elsewhere.
        stack.enter_context(patch.dict(sys.modules, {'ctypes.wintypes': N(RECT=_RECT, HWND=int)}))
        stack.enter_context(patch.object(ctypes, 'wintypes', N(RECT=_RECT, HWND=int), create=True))
        return stack

    def test_buttons_icon_and_margins(self):
        # 2026-10-13 うにさん：既定の幅では最小化ボタンがアイコンに重なっていた
        with patch.object(word_book.os, 'name', 'nt'), self.native():
            self.assertEqual(word_book.caption_width(N(winfo_id=lambda: 5)), 138 + 16 + 24)
            self.assertEqual(word_book.caption_width(None, hwnd=77), 178)

    def test_unknown_buttons_leave_the_width_alone(self):
        with patch.object(word_book.os, 'name', 'nt'), self.native(failed=1):
            self.assertIsNone(word_book.caption_width(None, hwnd=77))
        with patch.object(word_book.os, 'name', 'nt'), self.native(left=0, right=0):
            self.assertIsNone(word_book.caption_width(None, hwnd=77))
        with patch.object(word_book.os, 'name', 'posix'):
            self.assertIsNone(word_book.caption_width(None, hwnd=77))


if __name__ == '__main__':
    unittest.main()
