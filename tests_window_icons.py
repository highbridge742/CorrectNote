# -*- coding: utf-8 -*-
"""Native Windows icon handles and shell notifications on synthetic Tk windows."""
import sys,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import tkinter as tk
import app

@unittest.skipUnless(sys.platform=='win32','Windows taskbar integration')
class WindowIconTests(unittest.TestCase):
    def setUp(self):
        import ctypes
        from ctypes import wintypes as wt
        self.ctypes=ctypes;self.wt=wt
        self.u=ctypes.WinDLL('user32')
        self.u.SendMessageW.argtypes=(wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM)
        self.u.SendMessageW.restype=ctypes.c_ssize_t
        self.u.RegisterWindowMessageW.argtypes=(ctypes.c_wchar_p,)
        self.u.RegisterWindowMessageW.restype=wt.UINT
        self.root=tk.Tk();self.root.withdraw()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root
        self.a.settings={};self.a._win_controls=None;self.a._apply_border_color=Mock()
        self.a._on_files_dropped=Mock()
        self.a._apply_window_icon();self.a._setup_file_drop()
        self.hwnd=self.a._window_hwnd_win32(self.root)
        self.assertTrue(self.a._drop_hwnds,'Native notification callback not installed')
    def tearDown(self):
        self.a._teardown_file_drop();self.root.update_idletasks();self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def icons(self):return tuple(self.u.SendMessageW(self.hwnd,127,k,0) for k in (0,1))
    def test_icons_return_after_taskbar_created_messages(self):
        self.assertTrue(all(self.icons()))
        for name in ('TaskbarCreated','TaskbarButtonCreated'):
            for which in (0,1):self.u.SendMessageW(self.hwnd,128,which,0)
            self.assertEqual(self.icons(),(0,0),'Failed to simulate lost window icon handles')
            message=self.u.RegisterWindowMessageW(name)
            self.u.SendMessageW(self.hwnd,message,0,0)
            deadline=time.monotonic()+.5
            while time.monotonic()<deadline and not all(self.icons()):
                self.root.update();time.sleep(.004)
            self.assertEqual(self.icons(),(self.a._win_icon_small,self.a._win_icon_big),name)
    def test_root_notifications_are_coalesced_and_children_do_not_reapply_icons(self):
        child=tk.Text(self.root)
        with patch.object(self.a,'_set_window_icons_win32',return_value=True) as setter:
            for _ in range(100):self.a._queue_window_icons(SimpleNamespace(widget=child))
            self.root.update_idletasks();setter.assert_not_called()
            for _ in range(100):self.a._queue_window_icons(SimpleNamespace(widget=self.root))
            self.root.update_idletasks();setter.assert_called_once()
    def test_titlebar_modes_retain_valid_big_and_small_icon_handles(self):
        for hide in (True,False,True,False):
            self.a._apply_titlebar_visibility(hide)
            self.assertEqual(self.icons(),(self.a._win_icon_small,self.a._win_icon_big))

if __name__=='__main__':unittest.main()