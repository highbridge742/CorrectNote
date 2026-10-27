# -*- coding: utf-8 -*-
"""Quick input gives the focus back to the text box it was opened from.

2026-10-14 うにさん: on closing, the other app's text box is brought forward
and focused again, and (option, default on) the closed text is pasted there.
The other app here is a separate process with a native EDIT control."""
import ctypes as C
import os
import subprocess
import sys
import time
import unittest
from ctypes import wintypes as W
from unittest.mock import Mock, patch
import tkinter as tk

import quick_return
from selection_windows import Source

CHILD = r'''
import ctypes as C, sys, tkinter as tk
from ctypes import wintypes as W
u = C.WinDLL('user32')
u.CreateWindowExW.argtypes = (W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int,
                              C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p)
u.CreateWindowExW.restype = W.HWND
u.GetParent.argtypes = (W.HWND,); u.GetParent.restype = W.HWND
u.SendMessageW.argtypes = (W.HWND, W.UINT, C.c_size_t, C.c_void_p); u.SendMessageW.restype = C.c_ssize_t
root = tk.Tk(); root.title('quick-return-target'); root.geometry('300x120+700+400'); root.update()
edit = u.CreateWindowExW(0, 'EDIT', '', 0x50010000 | 0x4, 5, 5, 280, 100, root.winfo_id(), None, None, None)
top = u.GetParent(root.winfo_id()) or root.winfo_id()
pid = W.DWORD(); tid = u.GetWindowThreadProcessId(top, C.byref(pid))
print(int(top), int(edit), pid.value, tid, flush=True)
def read():
    buf = C.create_unicode_buffer(1000); u.SendMessageW(edit, 0x0D, 1000, C.cast(buf, C.c_void_p))
    print('TEXT', buf.value, flush=True)
    root.after(200, read)
root.after(200, read)
root.after(15000, root.destroy)
root.mainloop()
'''


class QuickReturnRulesTests(unittest.TestCase):
    def test_text_box_classes(self):
        for name in ('Edit', 'RichEdit20W', 'RICHEDIT50W', 'RichEditD2DPT', 'Scintilla', 'Notepad'):
            self.assertTrue(quick_return.is_text_class(name), name)
        for name in ('Button', 'SysListView32', 'Chrome_WidgetWin_1', ''):
            self.assertFalse(quick_return.is_text_class(name), name)

    def test_web_content_is_a_place_to_paste_but_explorer_and_excel_are_not(self):
        # 2026-10-19: a browser page draws its own caret; Ctrl+V on a part that takes no text does nothing
        for name in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0', 'Chrome_RenderWidgetHostHWND', 'MozillaWindowClass'):
            self.assertTrue(quick_return.is_web_content(name), name)
        for name in ('CabinetWClass', 'DirectUIHWND', 'SysListView32', 'XLMAIN', 'EXCEL7', 'Button', 'Edit', ''):
            self.assertFalse(quick_return.is_web_content(name), name)

    def test_capture_counts_a_browser_page_without_a_caret(self):
        source = Source(11, 12, os.getpid() + 1, 13)
        with patch.object(quick_return, 'class_name', return_value='Chrome_WidgetWin_1'), \
                patch('quick_ime._api') as api:
            api.return_value.GetGUIThreadInfo.return_value = 0
            self.assertTrue(quick_return.capture(source).text_box)
        with patch.object(quick_return, 'class_name', return_value='CabinetWClass'), \
                patch('quick_ime._api') as api:
            api.return_value.GetGUIThreadInfo.return_value = 0
            self.assertFalse(quick_return.capture(source).text_box)

    def test_only_another_apps_control_is_a_target(self):
        self.assertIsNone(quick_return.capture(None))
        own = Source(1, 2, os.getpid(), 3)
        self.assertIsNone(quick_return.capture(own))

    def test_nothing_happens_for_a_non_text_target_or_when_not_in_front(self):
        root = Mock()
        target = quick_return.Target(1, 2, 999999, 3, False)
        self.assertFalse(quick_return.restore(target, root, paste=True))
        root.after.assert_not_called()
        self.assertFalse(quick_return.restore(None, root, paste=True))

    def test_settings_default_on(self):
        from settings import Settings
        self.assertTrue(Settings().get('quick_paste_back'))


@unittest.skipUnless(sys.platform == 'win32', 'Windows focus')
class QuickReturnWindowsTests(unittest.TestCase):
    def setUp(self):
        # 本物の窓で前面と焦点を戻すところまで見る。Ctrl+V は送らず、門で止めた数を見る（2026-10-27。
        # 前面が人の窓に替わっていると、本物の Ctrl+V がそちらへ行ってしまうため）
        saved = os.environ.get('CORRECTNOTE_NO_EXTERNAL_PASTE')
        os.environ['CORRECTNOTE_NO_EXTERNAL_PASTE'] = '1'
        self.addCleanup(lambda: os.environ.pop('CORRECTNOTE_NO_EXTERNAL_PASTE', None) if saved is None
                        else os.environ.__setitem__('CORRECTNOTE_NO_EXTERNAL_PASTE', saved))
        quick_return.SENT.clear()
        self.child = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', CHILD],
                                      stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                      text=True, encoding='utf-8')
        top, edit, pid, tid = map(int, self.child.stdout.readline().split())
        self.source = Source(top, edit, pid, tid)
        self.root = tk.Tk(); self.root.title('quick-return-test'); self.root.geometry('200x80+60+60')

    def tearDown(self):
        try:
            self.root.destroy()
        finally:
            self.child.kill(); self.child.wait(); self.child.stdout.close()

    def last_text(self, seconds=2.0):
        import threading
        lines = []
        def reader():
            for line in self.child.stdout:
                if line.startswith('TEXT'):
                    lines.append(line[5:].rstrip('\n'))
        threading.Thread(target=reader, daemon=True).start()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(.02)
        return lines[-1] if lines else None

    def test_focus_goes_back_and_the_text_is_pasted(self):
        target = quick_return.capture(self.source)
        self.assertTrue(target.text_box)
        self.root.focus_force(); self.root.update()
        u = quick_return._user()
        for _ in range(20):
            if quick_return._ours_in_front():
                break
            self.root.lift(); self.root.focus_force(); self.root.update(); time.sleep(.05)
        if not quick_return._ours_in_front():
            self.skipTest('this desktop does not let the test window come to the front')
        self.root.clipboard_clear(); self.root.clipboard_append('簡易入力の文')
        self.assertTrue(quick_return.restore(target, self.root, paste=True))
        self.assertEqual(int(u.GetForegroundWindow() or 0), self.source.foreground)
        end = time.monotonic() + 2.0
        while time.monotonic() < end and not quick_return.SENT:
            self.root.update(); time.sleep(.02)
        self.assertEqual(quick_return.SENT, ['ctrl+v'])     # 貼る1回（門で止めた）

    def test_a_visit_to_another_app_meanwhile_still_goes_back(self):
        """2026-10-19 うにさん: opened from A, the user went to app B, came back to quick
        input and closed it. Given back before the quick window is destroyed, A is in
        front afterwards; asked after the destroy, B (the window used last) is."""
        other = subprocess.Popen([sys.executable, '-X', 'utf8', '-c',
                                  CHILD.replace("'300x120+700+400'", "'300x120+1050+400'")],
                                 stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding='utf-8')
        try:
            b_top = int(other.stdout.readline().split()[0])
            u = quick_return._user()
            k = C.WinDLL('kernel32')
            u.GetParent.argtypes = (W.HWND,); u.GetParent.restype = W.HWND

            def front(hwnd):
                fg = u.GetForegroundWindow(); me = k.GetCurrentThreadId()
                them = u.GetWindowThreadProcessId(fg, None) if fg else 0
                joined = bool(them and them != me and u.AttachThreadInput(me, them, True))
                try:
                    u.SetForegroundWindow(hwnd); u.BringWindowToTop(hwnd)
                finally:
                    if joined:
                        u.AttachThreadInput(me, them, False)
                end = time.monotonic() + .3
                while time.monotonic() < end:
                    self.root.update(); time.sleep(.02)
                return int(u.GetForegroundWindow() or 0) == int(hwnd)

            target = quick_return.capture(self.source)
            for order in ('given back first',):
                quick = tk.Toplevel(self.root); quick.geometry('200x60+400+300'); self.root.update()
                q = int(u.GetParent(quick.winfo_id()) or quick.winfo_id())
                if not (front(self.source.foreground) and front(q) and front(b_top) and front(q)):
                    quick.destroy()
                    self.skipTest('this desktop does not let the test windows come to the front')
                if order == 'given back first':
                    self.assertTrue(quick_return.restore(target, self.root, paste=False))
                    quick.destroy()
                    end = time.monotonic() + .3
                    while time.monotonic() < end:
                        self.root.update(); time.sleep(.02)
                    self.assertEqual(int(u.GetForegroundWindow() or 0), self.source.foreground, order)
                else:
                    quick.destroy()
                    end = time.monotonic() + .3
                    while time.monotonic() < end:
                        self.root.update(); time.sleep(.02)
                    self.assertEqual(int(u.GetForegroundWindow() or 0), b_top, order)
                    self.assertFalse(quick_return.restore(target, self.root, paste=False), order)
        finally:
            other.kill(); other.wait(); other.stdout.close()


if __name__ == '__main__':
    unittest.main()
