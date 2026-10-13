# -*- coding: utf-8 -*-
"""Emoji from the Windows emoji panel (Win+.) arrive as an IME result string.

2026-10-13 うにさん「Windows+.で候補が出るウインドウをクリックしても、絵文字が
入らない」: Tk 8.6.9 drops characters outside the BMP when they come as
WM_IME_COMPOSITION/GCS_RESULTSTR. The app takes them in its window subclass and
types them in through Tk's own insert procedure."""
import sys,time,unittest
from unittest.mock import Mock
import tkinter as tk
import app


class ImeResultNeedsHelpTests(unittest.TestCase):
    def test_only_text_outside_the_bmp_needs_help(self):
        self.assertTrue(app.ime_result_needs_help('\U0001F600'))
        self.assertTrue(app.ime_result_needs_help('あ\U0001F44D'))
        self.assertTrue(app.ime_result_needs_help('\ud83d'))
        for text in ('', None, 'あ', '漢字', 'abc', '★☆♪'):
            self.assertFalse(app.ime_result_needs_help(text), text)


class InsertImeTextTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root
        # The root stays withdrawn: say which field has the focus.
        self.focus=None;self.root.focus_get=lambda:self.focus
    def tearDown(self):
        self.root.destroy()
    def test_inserts_at_the_cursor_and_replaces_the_selection(self):
        w=tk.Text(self.root);w.pack();w.insert('1.0','前後');w.mark_set('insert','1.1')
        self.focus=w
        self.assertTrue(self.a._insert_ime_text('\U0001F600'))
        self.assertEqual(w.get('1.0','end-1c'),'前\U0001F600後')
        w.tag_add('sel','1.0','1.1');w.mark_set('insert','1.1')   # as a mouse selection leaves it
        self.assertTrue(self.a._insert_ime_text('\U0001F44D'))
        self.assertEqual(w.get('1.0','end-1c'),'\U0001F44D\U0001F600後')
    def test_entries_take_it_and_read_only_fields_do_not(self):
        e=tk.Entry(self.root);e.pack();e.insert(0,'ab');e.icursor(1)
        self.focus=e
        self.assertTrue(self.a._insert_ime_text('\U0001F600'))
        self.assertEqual(e.get(),'a\U0001F600b')
        w=tk.Text(self.root);w.pack();w.insert('1.0','x');w.config(state='disabled')
        self.focus=w
        self.assertFalse(self.a._insert_ime_text('\U0001F600'))
        self.assertEqual(w.get('1.0','end-1c'),'x')


@unittest.skipUnless(sys.platform=='win32','IMM32 on Windows')
class ImeEmojiThroughTheWindowTests(unittest.TestCase):
    """The same path the emoji panel takes: an IME result string, completed."""
    def setUp(self):
        import ctypes
        from ctypes import wintypes as wt
        self.u=ctypes.WinDLL('user32');self.imm=imm=ctypes.WinDLL('imm32')
        imm.ImmGetContext.restype=wt.HANDLE;imm.ImmGetContext.argtypes=[wt.HWND]
        imm.ImmReleaseContext.argtypes=[wt.HWND,wt.HANDLE]
        imm.ImmSetCompositionStringW.argtypes=[wt.HANDLE,wt.DWORD,ctypes.c_wchar_p,
                                               wt.DWORD,ctypes.c_void_p,wt.DWORD]
        imm.ImmNotifyIME.argtypes=[wt.HANDLE,wt.DWORD,wt.DWORD,wt.DWORD]
        imm.ImmSetOpenStatus.argtypes=[wt.HANDLE,wt.BOOL]
        imm.ImmGetOpenStatus.argtypes=[wt.HANDLE]
        self.root=tk.Tk();self.root.geometry('300x120+40+40')
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root
        self.a.settings={};self.a._win_controls=None;self.a._apply_border_color=Mock()
        self.a._on_files_dropped=Mock()
        self.a._setup_file_drop()
        self.assertTrue(self.a._drop_hwnds,'Native window subclass not installed')
        self.w=tk.Text(self.root);self.w.pack();self.root.update()
    def tearDown(self):
        self.a._teardown_file_drop();self.root.update_idletasks();self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root','w')
    def complete(self,text):
        self.w.delete('1.0','end');self.w.focus_force();self.root.update()
        h=self.u.GetFocus() or self.w.winfo_id()
        himc=self.imm.ImmGetContext(h)
        if not himc:self.skipTest('No input context (IME unavailable)')
        was=self.imm.ImmGetOpenStatus(himc);self.imm.ImmSetOpenStatus(himc,True)
        try:
            if not self.imm.ImmSetCompositionStringW(himc,9,text,len(text.encode('utf-16-le')),None,0):
                self.skipTest('IME does not accept a composition string here')
            self.imm.ImmNotifyIME(himc,0x15,1,0)
            deadline=time.monotonic()+1.0
            while time.monotonic()<deadline and self.w.get('1.0','end-1c')!=text:
                self.root.update();time.sleep(.01)
        finally:
            self.imm.ImmSetOpenStatus(himc,was);self.imm.ImmReleaseContext(h,himc)
        return self.w.get('1.0','end-1c')
    def test_emoji_and_kana_results_both_arrive_once(self):
        self.assertEqual(self.complete('あ'),'あ')
        self.assertEqual(self.complete('\U0001F600'),'\U0001F600')
        for _ in range(20):self.root.update();time.sleep(.01)
        self.assertEqual(self.w.get('1.0','end-1c'),'\U0001F600')


if __name__=='__main__':
    unittest.main()
