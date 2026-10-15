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

@unittest.skipUnless(sys.platform=='win32','Windows taskbar integration')
class StartupIconWaitTests(unittest.TestCase):
    """2026-10-13 うにさん「起動中、タスクバーの左端のアイコンが表示されないことが多い」:
    during __init__ the main window is not mapped just to receive icons; the
    first idle refresh (after the window is shown) gives them."""
    def setUp(self):
        self.root=tk.Tk()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root
        self.a._icons_wait_for_map=True
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def test_startup_does_not_map_the_window_for_icons(self):
        self.assertFalse(self.a._set_window_icons_win32())
        self.assertFalse(self.root.winfo_ismapped())
        # Another window (the quick input) is not held back.
        other=tk.Toplevel(self.root)
        with patch.object(self.a,'_window_hwnd_win32',return_value=None) as hwnd:
            self.a._set_window_icons_win32(other)
        hwnd.assert_called_once_with(other)
    def test_first_idle_refresh_shows_icons_on_the_window(self):
        # As in __init__: the first idle refresh, and the root's <Map> (icons sent
        # before Tk builds the frame are lost, so the map gives them again).
        self.root.bind('<Map>',self.a._queue_window_icons,add='+')
        self.a._queue_window_icons()
        for _ in range(3):self.root.update()
        self.assertFalse(self.a._icons_wait_for_map)
        import ctypes
        u=ctypes.WinDLL('user32')
        u.SendMessageW.argtypes=(ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p)
        u.SendMessageW.restype=ctypes.c_void_p
        hwnd=self.a._window_hwnd_win32(self.root)
        self.assertTrue(u.SendMessageW(hwnd,127,0,0))   # WM_GETICON ICON_SMALL
        self.assertTrue(u.SendMessageW(hwnd,127,1,0))   # ICON_BIG
    def test_handle_work_waits_for_the_first_map(self):
        # 2026-10-14: the drop setup (and the word book) took the HWND inside
        # __init__, which showed the window early while it could not answer
        # the taskbar. They now run after the window has appeared.
        calls=[]
        self.root.bind('<Map>',self.a._queue_window_icons,add='+')
        self.a._run_after_first_map(lambda:calls.append(self.root.winfo_ismapped()))
        self.assertEqual(calls,[])
        # An idle pass before the window is mapped keeps waiting.
        self.a._queue_window_icons()
        self.root.withdraw();self.root.update_idletasks()
        self.assertEqual(calls,[]);self.assertTrue(self.a._icons_wait_for_map)
        self.root.deiconify()
        for _ in range(5):self.root.update()
        self.assertEqual(calls,[1]);self.assertFalse(self.a._icons_wait_for_map)
        # Once shown, work runs at once.
        self.a._run_after_first_map(lambda:calls.append('now'))
        self.assertEqual(calls,[1,'now'])
    def test_word_book_opens_once_after_the_root_map(self):
        from types import SimpleNamespace as E
        opened=[]
        self.a._word_book=E(restore=lambda:opened.append(1));self.a._word_book_restore_pending=True
        other=tk.Toplevel(self.root)
        self.a._restore_word_book_after_map(E(widget=other))
        self.root.update();self.assertEqual(opened,[])
        self.a._restore_word_book_after_map(E(widget=self.root))
        self.a._restore_word_book_after_map(E(widget=self.root))
        self.root.update();self.assertEqual(opened,[1])
        self.a._word_book=None;other.destroy();other=None

if __name__=='__main__':unittest.main()