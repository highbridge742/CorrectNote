# -*- coding: utf-8 -*-
"""A conversion left in CorrectNote while another app is in front does not hold the work.

2026-10-19 うにさん: another window in front, CorrectNote behind; the row numbers kept
showing "not analysed" until a click on CorrectNote. The rows' marks (boundary_colors), the
automatic correction, quick input and the input-method reanalysis waited for "the IME is
converting" — read as "an unconfirmed string is left in the context", which stays there while
the window has no focus. Now they wait only while CorrectNote is in front (ime_watch.
composition_live); when the foreground cannot be told, as before."""
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import ime_watch


class LiveCompositionRuleTests(unittest.TestCase):
    def test_left_conversion_does_not_count_while_another_app_is_in_front(self):
        with patch.object(ime_watch, 'composition_active', return_value=True), \
                patch.object(ime_watch, '_foreground_process', return_value=os.getpid() + 1):
            self.assertFalse(ime_watch.composition_live(123))
        with patch.object(ime_watch, 'composition_active', return_value=True), \
                patch.object(ime_watch, '_foreground_process', return_value=os.getpid()):
            self.assertTrue(ime_watch.composition_live(123))         # typing in CorrectNote: unchanged
        with patch.object(ime_watch, 'composition_active', return_value=True), \
                patch.object(ime_watch, '_foreground_process', return_value=None):
            self.assertTrue(ime_watch.composition_live(123))         # cannot tell: as before
        for value in (False, None):
            with patch.object(ime_watch, 'composition_active', return_value=value), \
                    patch.object(ime_watch, '_foreground_process', return_value=os.getpid()):
                self.assertEqual(ime_watch.composition_live(123), value)

    def test_every_wait_uses_the_live_check(self):
        root = Path(ime_watch.__file__).resolve().parent
        def body(path, name):
            import ast
            source = (root / path).read_text(encoding='utf-8')
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.FunctionDef) and node.name == name:
                    return ast.get_source_segment(source, node)
            raise AssertionError((path, name))
        for path, name in (('boundary_colors.py', '_composing'), ('quick_analysis.py', '_composing'),
                           ('app.py', '_apply_unified_autofix'), ('app.py', '_run_input_method_reanalyze')):
            src = body(path, name)
            self.assertIn('composition_live(', src, (path, name))
            self.assertNotIn('composition_active(', src, (path, name))


class PendingNoteTests(unittest.TestCase):
    """Rows marked "not analysed" for 5 s or more: the bottom line says what is waited for."""
    def setUp(self):
        import tkinter as tk
        import app
        self.app_module = app
        self.root = tk.Tk(); self.root.withdraw()
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.status = tk.Label(self.root, text='')
        a.editor = tk.Text(self.root)
        a._queue_status_visibility = lambda: None
        a._view_changing = lambda: False
        a._foreground_analysis_pending = lambda: False
        a._after_id = 'job'
        self.a = a

    def tearDown(self):
        self.root.destroy()

    def test_reasons(self):
        a = self.a
        with patch.object(ime_watch, 'composition_live', return_value=False):
            self.assertIsNone(a._analysis_wait_reason())
            a._tab_warming = True
            self.assertIn('タブの切り替え', a._analysis_wait_reason())
            a._tab_warming = False
            a._after_id = None; a._analyze_job = None; a._tab_analysis_job = None
            self.assertIn('予約がありません', a._analysis_wait_reason())
        with patch.object(ime_watch, 'composition_live', return_value=True):
            self.assertIn('変換（未確定の文字）', a._analysis_wait_reason())

    def test_note_appears_after_five_seconds_and_goes_away(self):
        a = self.a
        clock = [100.0]
        pending = [True]
        a._visible_rows_pending = lambda: pending[0]
        a._analysis_wait_reason = lambda: '変換を待っています'
        with patch.object(self.app_module.time, 'monotonic', lambda: clock[0]):
            a._watch_pending_marks(); self.assertEqual(a.status.cget('text'), '')
            clock[0] += 4.9; a._watch_pending_marks(); self.assertEqual(a.status.cget('text'), '')
            clock[0] += 0.2; a._watch_pending_marks()
            self.assertEqual(a.status.cget('text'), '未解析の行が残っています：変換を待っています')
            pending[0] = False; a._watch_pending_marks()
            self.assertEqual(a.status.cget('text'), '')
            # another message on the line is not overwritten
            a.status.config(text='保存しました'); pending[0] = True
            a._watch_pending_marks(); clock[0] += 6; a._watch_pending_marks()
            self.assertEqual(a.status.cget('text'), '保存しました')
        job = getattr(a, '_pending_watch_job', None)
        if job is not None:
            self.root.after_cancel(job)


@unittest.skipUnless(sys.platform == 'win32', 'Windows focus')
class LiveCompositionWindowsTests(unittest.TestCase):
    """Own windows only: a Tk Text here with a conversion left in its IME context, and a
    child process window that comes to the front."""
    def test_left_conversion_in_a_window_behind(self):
        import ctypes as C
        from ctypes import wintypes as W
        import tkinter as tk
        import quick_return
        from tests_quick_return import CHILD
        child = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', CHILD.replace("'300x120+700+400'", "'260x90+1000+520'")],
                                 stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding='utf-8')
        root = tk.Tk(); root.geometry('240x90+400+520')
        try:
            other_top = int(child.stdout.readline().split()[0])
            text = tk.Text(root); text.pack(); root.update()
            hwnd = text.winfo_id()
            u = quick_return._user(); k = C.WinDLL('kernel32')
            u.GetParent.argtypes = (W.HWND,); u.GetParent.restype = W.HWND
            ours = int(u.GetParent(root.winfo_id()) or root.winfo_id())

            def front(target):
                fg = u.GetForegroundWindow(); me = k.GetCurrentThreadId()
                them = u.GetWindowThreadProcessId(fg, None) if fg else 0
                joined = bool(them and them != me and u.AttachThreadInput(me, them, True))
                try:
                    u.SetForegroundWindow(target); u.BringWindowToTop(target)
                finally:
                    if joined:
                        u.AttachThreadInput(me, them, False)
                end = time.monotonic() + .3
                while time.monotonic() < end:
                    root.update(); time.sleep(.02)
                return int(u.GetForegroundWindow() or 0) == int(target)

            imm = C.WinDLL('imm32')
            imm.ImmGetContext.argtypes = (W.HWND,); imm.ImmGetContext.restype = W.HANDLE
            imm.ImmReleaseContext.argtypes = (W.HWND, W.HANDLE)
            imm.ImmSetOpenStatus.argtypes = (W.HANDLE, W.BOOL)
            imm.ImmSetCompositionStringW.argtypes = (W.HANDLE, W.DWORD, C.c_wchar_p, W.DWORD, C.c_void_p, W.DWORD)
            imm.ImmNotifyIME.argtypes = (W.HANDLE, W.DWORD, W.DWORD, W.DWORD)
            if not front(ours):
                self.skipTest('this desktop does not let the test window come to the front')
            himc = imm.ImmGetContext(hwnd)
            if not himc:
                self.skipTest('no IME context')
            try:
                imm.ImmSetOpenStatus(himc, True)
                left = 'のこった'
                if not imm.ImmSetCompositionStringW(himc, 9, left, len(left) * 2, None, 0):
                    self.skipTest('this IME does not take a composition set by the program')
            finally:
                imm.ImmReleaseContext(hwnd, himc)
            root.update()
            self.assertTrue(ime_watch.composition_active(hwnd))
            self.assertTrue(ime_watch.composition_live(hwnd))        # ours in front: it is being typed
            if not front(other_top):
                self.skipTest('this desktop does not let the other window come to the front')
            if ime_watch.composition_active(hwnd):
                # the conversion is still left in our context: it must not count while we are behind
                self.assertFalse(ime_watch.composition_live(hwnd))
            himc = imm.ImmGetContext(hwnd)
            if himc:
                imm.ImmNotifyIME(himc, 0x15, 4, 0); imm.ImmSetOpenStatus(himc, False)
                imm.ImmReleaseContext(hwnd, himc)
        finally:
            root.destroy()
            child.kill(); child.wait(); child.stdout.close()


if __name__ == '__main__':
    unittest.main()
