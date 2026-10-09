# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Native foreground tracking has a bounded lifetime and safe fallback."""
import sys,unittest
from unittest.mock import patch

@unittest.skipUnless(sys.platform=='win32','Windows native window contract')
class WordBookFocusTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root=tk.Tk();self.root.withdraw();self.root.update_idletasks()
        self.native=None
    def tearDown(self):
        if self.native is not None:self.native.detach()
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'root')
    def test_unhook_on_detach_and_destroy(self):
        import word_book as W
        self.native=W._WordBookNative(self.root)
        native=self.native;hook=native.event_hook
        self.assertTrue(hook,native.hook_error)
        with patch.object(native.user,'UnhookWinEvent',wraps=native.user.UnhookWinEvent) as unhook:
            native.detach();native.detach()
            unhook.assert_called_once_with(hook)
        import tkinter as tk
        win=tk.Toplevel(self.root);win.update_idletasks()
        other=W._WordBookNative(win);hook=other.event_hook
        self.assertTrue(hook)
        with patch.object(other.user,'UnhookWinEvent',wraps=other.user.UnhookWinEvent) as unhook:
            win.destroy();other.detach()
            unhook.assert_called_once_with(hook)
        self.assertIsNone(other.event_hook);self.assertIsNone(other.hwnd)

    def test_unavailable_event_hook_retains_window_message_fallback(self):
        import word_book as W
        import ctypes as c
        from ctypes import wintypes as T
        import tkinter as tk
        self.native=W._WordBookNative(self.root)
        native=self.native;native._remove_foreground_hook()
        with patch.object(native.user,'SetWinEventHook',return_value=0):
            native._install_foreground_hook()
        self.assertFalse(native.event_hook)
        peer=tk.Toplevel(self.root);peer.update_idletasks()
        try:
            hwnd=native.user.GetAncestor(peer.winfo_id(),2)
            native.user.SendMessageW.argtypes=[T.HWND,T.UINT,c.c_size_t,c.c_ssize_t]
            native.user.SendMessageW.restype=c.c_ssize_t
            # This synthetic activation tests our fallback, not Windows'
            # default activation (which may synchronously activate another
            # window and send a second WM_ACTIVATE on the CI desktop).
            with patch.object(native.comctl,'DefSubclassProc',return_value=0) as forward:
                native.user.SendMessageW(native.hwnd,6,2,hwnd)
            forward.assert_called_once_with(native.hwnd,6,2,hwnd)
            self.assertEqual(native.previous[0],hwnd)
        finally:peer.destroy()

if __name__=='__main__':unittest.main()
