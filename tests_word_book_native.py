# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Native window remains usable if the optional shell registration fails."""
import sys,unittest
from unittest.mock import patch

@unittest.skipUnless(sys.platform=='win32','Windows native window contract')
class WordBookTaskbarFailureTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root=tk.Tk();self.root.withdraw();self.root.update_idletasks()
        self.native=None
    def tearDown(self):
        if self.native is not None:self.native.detach()
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'root')
    def test_missing_shell_keeps_native_window_and_cleanup(self):
        import word_book as W
        with patch.object(W,'_TaskbarButton',side_effect=OSError('no shell')):
            self.native=W._WordBookNative(self.root)
        native=self.native
        self.assertTrue(native.hwnd);self.assertIsNone(native.taskbar)
        self.assertEqual(native.taskbar_error,'no shell')
        native.show_taskbar();native.detach()
        self.assertIsNone(native.hwnd)
    def test_failed_addtab_releases_shell_and_keeps_window_hook(self):
        import word_book as W
        calls=[];closed=[]
        class Shell:
            def call(self,slot,hwnd=None):calls.append(slot);return -1 if slot==4 else 0
            def close(self):closed.append(True)
        with patch.object(W,'_TaskbarButton',Shell):self.native=W._WordBookNative(self.root)
        native=self.native;hwnd=native.hwnd
        native.show_taskbar();native.show_taskbar()
        self.assertEqual(calls,[4,5]);self.assertEqual(closed,[True])
        self.assertEqual(native.hwnd,hwnd);self.assertIsNone(native.taskbar)
        self.assertEqual(native.taskbar_error,'Cannot add word book to taskbar')
        native.detach();native.detach();self.assertEqual(closed,[True])
    def test_successful_shell_add_and_remove_are_preserved(self):
        import word_book as W
        calls=[];closed=[]
        class Shell:
            def call(self,slot,hwnd=None):calls.append((slot,hwnd));return 0
            def close(self):closed.append(True)
        with patch.object(W,'_TaskbarButton',Shell):self.native=W._WordBookNative(self.root)
        native=self.native;hwnd=native.hwnd
        native.show_taskbar()
        self.assertIsNone(native.taskbar_error);self.assertIsNotNone(native.taskbar)
        native.detach()
        self.assertEqual(calls,[(4,hwnd),(5,hwnd)]);self.assertEqual(closed,[True])

if __name__=='__main__':unittest.main()
