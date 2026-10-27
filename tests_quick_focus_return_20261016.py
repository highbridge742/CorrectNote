# -*- coding: utf-8 -*-
"""Quick input remembers the box it was opened from once, and goes back there.

2026-10-16 うにさん「別ウインドウのテキストボックスフォーカスから簡易入力を開き、
また別のアプリをアクティブにしてから簡易入力を閉じると、最初のテキストボックスを
フォーカスしない。フォーカスできるか検討する。」

Cause: bringing a minimized quick window back with the shortcut went through the
"new opening" path and replaced the remembered box with whatever was in front.
Now the box is remembered only when no quick window exists. On closing, the
paste happens only once the original window really is in front again.
Win32 calls are replaced here: no real window is brought forward.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import quick_return
from quick_selection import SelectionOpening
from selection_windows import Source

A = Source(0x100, 0x101, os.getpid() + 1, 11)       # the box quick input was opened from
B = Source(0x200, 0x201, os.getpid() + 2, 22)       # another app, in front later


class FakeWindow:
    def __init__(self, state='normal'):
        self._state = state

    def winfo_exists(self):
        return True

    def state(self):
        return self._state


class RememberOnceTests(unittest.TestCase):
    def opener(self, app, source):
        return SelectionOpening(app, reader=lambda *a: None, snapshot=lambda: source)

    def app(self):
        return SimpleNamespace(root=Mock(), _show_quick_capture=Mock(), _quick_win=None)

    def open(self, app, source):
        with patch('quick_ime.foreground_fullwidth_mode', return_value=None), \
                patch.object(quick_return, 'class_name', return_value='Edit'):
            self.opener(app, source).open(None)

    def test_first_opening_remembers_the_box(self):
        app = self.app()
        self.open(app, A)
        self.assertEqual(app._quick_return, quick_return.Target(A.foreground, A.focus, A.process, A.thread, True))

    def test_bringing_back_a_minimized_window_keeps_the_first_box(self):
        app = self.app()
        self.open(app, A)
        first = app._quick_return
        app._quick_win = FakeWindow('iconic')
        self.open(app, B)                    # shortcut pressed while app B is in front
        self.assertEqual(app._quick_return, first)
        self.open(app, Source(0x300, 0x301, os.getpid(), 33))   # ... or CorrectNote itself
        self.assertEqual(app._quick_return, first)

    def test_bringing_forward_an_open_window_keeps_the_first_box(self):
        app = self.app()
        self.open(app, A)
        first = app._quick_return
        app._quick_win = FakeWindow('normal')
        self.open(app, B)
        self.assertEqual(app._quick_return, first)
        app._show_quick_capture.assert_called()

    def test_a_new_window_after_closing_remembers_again(self):
        app = self.app()
        self.open(app, A)
        app._quick_win = None                # closed
        self.open(app, B)
        self.assertEqual(app._quick_return.foreground, B.foreground)


class FakeUser:
    """Stands in for user32: who is in front, and what was asked."""

    def __init__(self, front, comes_forward=True, alive=True):
        self.front, self.comes_forward, self.alive = front, comes_forward, alive
        self.keys, self.calls = [], []

    def IsWindow(self, h):
        return self.alive

    def IsIconic(self, h):
        return False

    def ShowWindow(self, h, n):
        self.calls.append(('ShowWindow', h))

    def SetForegroundWindow(self, h):
        self.calls.append(('SetForegroundWindow', h))
        if self.comes_forward:
            self.front = h
        return self.comes_forward

    def BringWindowToTop(self, h):
        self.calls.append(('BringWindowToTop', h))

    def SetFocus(self, h):
        self.calls.append(('SetFocus', h))

    def AttachThreadInput(self, a, b, on):
        self.calls.append(('AttachThreadInput', b, bool(on)))
        return True

    def GetForegroundWindow(self):
        return self.front

    def keybd_event(self, vk, scan, flags, extra):
        self.keys.append((vk, flags))


class GoBackTests(unittest.TestCase):
    target = quick_return.Target(A.foreground, A.focus, A.process, A.thread, True)

    def restore(self, user, paste=True):
        root = Mock()
        root.after.side_effect = lambda ms, fn: fn()
        # FakeUser の keybd_event に届くかを見るので、外へ送る門（CORRECTNOTE_NO_EXTERNAL_PASTE）はここだけ開ける
        with patch.object(quick_return, '_user', return_value=user), \
                patch.object(quick_return, 'external_input_blocked', return_value=False), \
                patch.object(quick_return, '_ours_in_front', return_value=True), \
                patch.object(quick_return.sys, 'platform', 'win32'):
            return quick_return.restore(self.target, root, paste=paste), root

    def test_goes_back_to_the_first_box_and_pastes(self):
        user = FakeUser(front=0x999)
        done, root = self.restore(user)
        self.assertTrue(done)
        self.assertIn(('SetForegroundWindow', A.foreground), user.calls)
        self.assertIn(('SetFocus', A.focus), user.calls)
        # The input threads are joined only while switching, then separated.
        attach = [c for c in user.calls if c[0] == 'AttachThreadInput']
        self.assertEqual(attach, [('AttachThreadInput', A.thread, True), ('AttachThreadInput', A.thread, False)])
        self.assertEqual(user.keys, [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)])

    def test_window_not_brought_forward_pastes_nowhere(self):
        user = FakeUser(front=B.foreground, comes_forward=False)
        done, root = self.restore(user)
        self.assertFalse(done)
        self.assertEqual(user.keys, [])
        root.after.assert_not_called()

    def test_closed_window_pastes_nowhere(self):
        user = FakeUser(front=B.foreground, alive=False)
        done, root = self.restore(user)
        self.assertFalse(done)
        self.assertEqual(user.keys, [])
        self.assertEqual(user.calls, [])


def child(case):
    """A real app in a copied folder: open quick input, close it; the way back is replaced."""
    import tkinter as tk
    sys.path.insert(0, os.getcwd())
    import app
    import quick_return as Q
    from session import new_tab
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                     encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='')])), encoding='utf8')
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear = lambda *a, **k: None
    root.clipboard_append = lambda *a, **k: None
    asked = []
    window_alive = []

    def give_back(target, root_, paste=False):
        asked.append(paste)
        # 2026-10-19: asked while the quick window still exists (in front)
        win = getattr(a, '_quick_win', None)
        window_alive.append(bool(win is not None and win.winfo_exists()))
        return case == 'back'
    a = None
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None), \
                patch.object(tk.Toplevel, 'winfo_pointerxy', return_value=(300, 200)), \
                patch.object(Q, 'restore', give_back):
            a = app.CorrectNoteApp(root)
            root.update()
            a._open_quick_capture()
            a._quick_text.insert('1.0', '閉じる文')
            a._quick_return = Q.Target(1, 2, 3, 4, True)
            a._close_quick_capture()
            print('RESULT ' + json.dumps(dict(asked=asked, window_alive=window_alive,
                                              closed=a._quick_win is None, status=a.status.cget('text'),
                                              memo=a.editor.get('1.0', 'end-1c')), ensure_ascii=False), flush=True)
    finally:
        if a:
            a._on_close()
        else:
            root.destroy()


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class CloseStatusTests(unittest.TestCase):
    def run_case(self, case):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-back-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):
                    shutil.copyfile(path, dest / path.name)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child', case],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8',
                                 timeout=150)
            line = next((l for l in run.stdout.splitlines() if l.startswith('RESULT ')), None)
            self.assertIsNotNone(line, run.stdout[-3000:])
            return json.loads(line[7:])

    def test_could_not_go_back_says_so_and_keeps_the_text_in_the_memo(self):
        r = self.run_case('stuck')
        self.assertEqual(r['asked'], [True])
        self.assertIn('元の入力欄に戻れなかったので貼り付けていません', r['status'])
        self.assertIn('閉じる文', r['memo'])

    def test_went_back(self):
        r = self.run_case('back')
        self.assertIn('元の入力欄へ戻しました', r['status'])
        self.assertNotIn('戻れなかった', r['status'])

    def test_focus_is_given_back_before_the_quick_window_is_destroyed(self):
        # 2026-10-19 うにさん: destroying the window in front makes Windows activate the
        # window used last (another app visited meanwhile); asked afterwards, the return
        # read that as "the user went elsewhere" and did not go back.
        for case in ('back', 'stuck'):
            r = self.run_case(case)
            self.assertEqual(r['window_alive'], [True], case)
            self.assertTrue(r['closed'], case)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1])
    else:
        unittest.main()
