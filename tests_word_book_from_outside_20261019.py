# -*- coding: utf-8 -*-
"""The word book button, clicked while another app is in front, does not make CorrectNote the
active app (2026-10-19 うにさん「別アプリアクティブ中に、本アプリの単語帳ボタンを直接クリック
した場合は、本アプリをアクティブにせずに、単語帳を開いてください」).

The button answers WM_MOUSEACTIVATE with MA_NOACTIVATE while another app is in front, and the
word book, once open, gives the front back to that app, so a click on a word pastes there.
With CorrectNote in front, both behave as before."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk

import word_book

# 試験の中では外の窓へキーを送らない（quick_return・文変換の門。子のプロセスにも引き継がれる・2026-10-27）
os.environ['CORRECTNOTE_NO_EXTERNAL_PASTE'] = '1'


class FromOutsideRuleTests(unittest.TestCase):
    def setUp(self):
        import no_activate
        self.no_activate = no_activate

    def test_other_app_in_front(self):
        na = self.no_activate
        with patch.object(na, '_foreground_process', return_value=os.getpid() + 1):
            self.assertTrue(na.other_app_in_front())
        with patch.object(na, '_foreground_process', return_value=os.getpid()):
            self.assertFalse(na.other_app_in_front())
        with patch.object(na, '_foreground_process', return_value=None), \
                patch.object(na.sys, 'platform', 'win32'):
            # no window in front at the moment of the click (うにさんの記録 2026-10-19:
            # front=0 on WM_MOUSEACTIVATE): that is not CorrectNote in front
            self.assertTrue(na.other_app_in_front())
        with patch.object(na.sys, 'platform', 'linux'):
            self.assertFalse(na.other_app_in_front())          # not Windows: as before

    def book(self):
        book = word_book.WordBook.__new__(word_book.WordBook)
        book.app = SimpleNamespace(root=Mock())
        book.app.root.after.side_effect = lambda ms, fn: fn()
        book.window = None
        book._native = None
        return book

    def test_opened_from_outside_gives_the_front_back(self):
        book = self.book()
        native = SimpleNamespace(previous=(0x55, os.getpid() + 1), restore_previous=Mock(return_value=True))
        def fake_open(give_back=False, outside=None):
            book.window = Mock(); book._native = native
            if give_back:
                book._give_back_after_open()
        with patch.object(word_book.WordBook, 'open', side_effect=fake_open):
            book.toggle(give_back=True)
        native.restore_previous.assert_called_once()

    def test_opened_from_inside_gives_the_focus_back_to_the_text(self):
        # 2026-10-19 (うにさんの記録): opened while typing in CorrectNote, Tk's deiconify still
        # made the word book the active window; the text being typed in gets the focus back
        book = self.book()
        text = Mock(); text.winfo_exists.return_value = True
        book.app.root.focus_get.return_value = text
        native = SimpleNamespace(previous=(0x77, os.getpid()), hwnd=0x99, restore_previous=Mock(),
                                 user=SimpleNamespace(GetForegroundWindow=lambda: 0x99))
        def fake_open(give_back=False, outside=None):
            book.window = Mock(); book._native = native
            book._give_back_after_open()
        with patch.object(word_book.WordBook, 'open', side_effect=fake_open):
            book.toggle()
        text.focus_force.assert_called_once()
        native.restore_previous.assert_not_called()
        # the focus already elsewhere (the book did not take it): nothing is moved
        text.focus_force.reset_mock(); book.window = None
        native.user = SimpleNamespace(GetForegroundWindow=lambda: 0x77)
        with patch.object(word_book.WordBook, 'open', side_effect=fake_open):
            book.toggle()
        text.focus_force.assert_not_called()

    def test_own_previous_window_is_not_given_back(self):
        book = self.book()
        book._native = SimpleNamespace(previous=(0x55, os.getpid()), restore_previous=Mock(return_value=True))
        book._give_back_after_open()
        book._native.restore_previous.assert_not_called()

    def test_minimized_book_comes_back_without_taking_the_front(self):
        book = self.book()
        book.window = Mock(); book.window.state.return_value = 'iconic'
        book._native = SimpleNamespace(previous=(0x55, os.getpid() + 1), restore_previous=Mock(return_value=True))
        book.toggle(give_back=True)
        book.window.deiconify.assert_called_once()
        book._native.restore_previous.assert_called_once()
        book.window.state.return_value = 'iconic'
        book._native.restore_previous.reset_mock()
        book.toggle()                                            # CorrectNote in front: as before
        book._native.restore_previous.assert_not_called()

    def test_open_book_closes_also_when_clicked_from_outside(self):
        # 2026-10-19 うにさん「ブラウザ前面の時、単語帳ボタンで単語帳を閉じられなくなりました。
        # ひとつ前バージョンではできました」: a shown word book closes, from inside and outside
        book = self.book()
        book.window = Mock(); book.window.state.return_value = 'normal'
        book._native = SimpleNamespace(previous=(0x55, os.getpid() + 1), restore_previous=Mock(return_value=True))
        with patch.object(word_book.WordBook, 'close') as close:
            book.toggle(give_back=True)
            close.assert_called_once()
            book.window.lift.assert_not_called()
            book.toggle()
            self.assertEqual(close.call_count, 2)

    def test_hotkey_toggles_the_word_book_like_the_button(self):
        # 2026-10-19 うにさん「Ctrl+Alt+Insert または Ctrl+Shift+Alt+- でどこからでも単語帳を
        # オンオフ」: from another app the front and its text box stay where they are
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._word_book = Mock()
        with patch.object(self.no_activate, 'other_app_in_front', return_value=True), \
                patch.object(self.no_activate, '_note_outside') as note, \
                patch.object(self.no_activate, 'recent_outside', return_value=(0x55, 77)):
            a._toggle_word_book_from_hotkey()
            note.assert_called_once()
        a._word_book.toggle.assert_called_with(give_back=True, outside=(0x55, 77))
        with patch.object(self.no_activate, 'other_app_in_front', return_value=False):
            a._toggle_word_book_from_hotkey()
        a._word_book.toggle.assert_called_with(give_back=False, outside=None)
        # the hotkey thread's box is read on the Tk thread: 'wordbook' toggles, others open quick input
        import queue
        a._hotkey_queue = queue.Queue(); a.root = Mock()
        a._toggle_word_book_from_hotkey = Mock(); a._open_quick_capture = Mock()
        a._hotkey_queue.put('wordbook'); a._hotkey_queue.put('minus')
        a._poll_hotkey_queue()
        a._toggle_word_book_from_hotkey.assert_called_once()
        a._open_quick_capture.assert_called_once_with('minus')

    def test_one_click_runs_the_command_once(self):
        # 2026-10-19 (うにさんの記録): one real click ran the command twice, ~30 ms apart, so
        # the book opened and closed at once ("初回は出ませんでした"・"出し直しています")
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._word_book = Mock()
        clock = [10.0]
        with patch.object(self.no_activate, 'other_app_in_front', return_value=False), \
                patch.object(app.time, 'monotonic', lambda: clock[0]), \
                patch.object(self.no_activate, 'posted_recently', return_value=True):
            a._toggle_word_book()
            clock[0] += 0.03; a._toggle_word_book()
            self.assertEqual(a._word_book.toggle.call_count, 1)
            clock[0] += 0.5; a._toggle_word_book()
            self.assertEqual(a._word_book.toggle.call_count, 2)
        # without a click from the button's subclass (a call from code), every call runs
        with patch.object(self.no_activate, 'other_app_in_front', return_value=False), \
                patch.object(app.time, 'monotonic', lambda: clock[0]), \
                patch.object(self.no_activate, 'posted_recently', return_value=False):
            clock[0] += 0.01; a._toggle_word_book()
            self.assertEqual(a._word_book.toggle.call_count, 3)

    def test_button_command_asks_for_the_give_back_only_from_outside(self):
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._word_book = Mock()
        with patch.object(self.no_activate, 'other_app_in_front', return_value=True), \
                patch.object(self.no_activate, 'recent_outside', return_value=(0x55, 77)):
            a._toggle_word_book()
        a._word_book.toggle.assert_called_with(give_back=True, outside=(0x55, 77))
        a._word_book_clicked_at = None
        with patch.object(self.no_activate, 'other_app_in_front', return_value=False):
            a._toggle_word_book()
        a._word_book.toggle.assert_called_with(give_back=False, outside=None)

    def test_the_app_in_front_is_remembered_before_the_click(self):
        # 2026-10-19 (うにさんの記録): at the click Windows already reports no window in front,
        # so the app to give the front back to is the one seen while the pointer was over the button
        na = self.no_activate
        na._LAST_OUTSIDE = None
        self.assertIsNone(na.recent_outside())
        clock = [100.0]
        with patch('time.monotonic', lambda: clock[0]):
            na._LAST_OUTSIDE = (0x55, 77, clock[0])
            self.assertEqual(na.recent_outside(), (0x55, 77))
            clock[0] += 31
            self.assertIsNone(na.recent_outside())
        na._LAST_OUTSIDE = None

    def test_give_front_and_restore_with_a_word_book_that_never_activates(self):
        native = word_book._WordBookNative.__new__(word_book._WordBookNative)
        native.hwnd = 0x99
        front = [0]
        native.user = SimpleNamespace(GetForegroundWindow=lambda: front[0], IsWindow=lambda h: True,
                                      IsIconic=lambda h: False, IsWindowVisible=lambda h: True,
                                      SetForegroundWindow=Mock(return_value=True),
                                      GetWindowThreadProcessId=lambda h, p: 1)
        native.c = __import__('ctypes')
        native.focus = None
        # nothing in front (as right after the click): the front goes back to the other app
        self.assertTrue(native.give_front(0x55))
        native.user.SetForegroundWindow.assert_called_once_with(0x55)
        # already in front: nothing to do; somewhere else: leave it
        native.user.SetForegroundWindow.reset_mock()
        front[0] = 0x55; self.assertTrue(native.give_front(0x55))
        front[0] = 0x66; self.assertFalse(native.give_front(0x55))
        native.user.SetForegroundWindow.assert_not_called()
        # a click on a word: the app it pastes into kept the front
        native.previous = (0x55, 77)
        front[0] = 0x55
        self.assertTrue(native.restore_previous())
        front[0] = 0x66
        self.assertFalse(native.restore_previous())


class FocusTraceTests(unittest.TestCase):
    def test_off_unless_the_switch_file_exists(self):
        import tempfile
        import focus_trace
        with tempfile.TemporaryDirectory() as d, patch.object(focus_trace, '_folder', return_value=d):
            with patch.object(focus_trace, '_ON', None):
                self.assertFalse(focus_trace.enabled())
                focus_trace.log('nothing')
            self.assertFalse(os.path.exists(os.path.join(d, 'word_book_trace.log')))
            open(os.path.join(d, 'word_book_trace.on'), 'w').close()
            with patch.object(focus_trace, '_ON', None):
                self.assertTrue(focus_trace.enabled())
                focus_trace.log('button', 'press')
            with open(os.path.join(d, 'word_book_trace.log'), encoding='utf-8') as f:
                self.assertRegex(f.read(), r'^\d+\.\d{3} button press\n$')


@unittest.skipUnless(sys.platform == 'win32', 'Windows activation')
class NoActivateButtonTests(unittest.TestCase):
    """The real subclass on a Tk button: WM_MOUSEACTIVATE is answered with MA_NOACTIVATE
    while another app is in front, and passed on as before otherwise."""
    def test_mouse_activate_answer(self):
        import ctypes as C
        from ctypes import wintypes as W
        import no_activate
        root = tk.Tk(); root.withdraw()
        try:
            button = tk.Button(root, text='単語帳'); button.pack(); root.update()
            self.assertTrue(no_activate.install(button))
            user = C.WinDLL('user32')
            user.SendMessageW.argtypes = (W.HWND, W.UINT, W.WPARAM, W.LPARAM); user.SendMessageW.restype = C.c_ssize_t
            top = int(root.wm_frame(), 16) if root.wm_frame() else 0
            lparam = (0x0201 << 16) | 1                         # WM_LBUTTONDOWN over the client area
            with patch.object(no_activate, 'other_app_in_front', return_value=True):
                self.assertEqual(user.SendMessageW(button.winfo_id(), 0x0021, top, lparam), 3)   # MA_NOACTIVATE
            with patch.object(no_activate, 'other_app_in_front', return_value=False):
                self.assertNotEqual(user.SendMessageW(button.winfo_id(), 0x0021, top, lparam), 3)
            button.destroy(); root.update()                       # the subclass goes with the window
        finally:
            root.destroy()

    def test_word_book_window_never_activates_and_stays_in_the_taskbar(self):
        import ctypes as C
        from ctypes import wintypes as W
        root = tk.Tk(); root.withdraw()
        try:
            win = tk.Toplevel(root); win.withdraw(); win.update_idletasks()
            native = word_book._WordBookNative(win)
            self.assertTrue(native.make_noactivate())
            user = C.WinDLL('user32')
            user.GetWindowLongPtrW.argtypes = (W.HWND, C.c_int); user.GetWindowLongPtrW.restype = C.c_ssize_t
            style = user.GetWindowLongPtrW(native.hwnd, -20)
            self.assertTrue(style & 0x08000000)       # WS_EX_NOACTIVATE
            self.assertTrue(style & 0x00040000)       # WS_EX_APPWINDOW
            native.detach()
        finally:
            root.destroy()

    def test_press_does_not_take_the_focus_and_release_runs_the_command(self):
        """A real click also reaches the native BUTTON control, which takes the keyboard focus
        on WM_LBUTTONDOWN — and that activates CorrectNote's window (うにさん 2026-10-19:
        「アプリが前面に出て下がりませんでした」). With another app in front the press must not
        reach the control, and the release must still run the button's command."""
        import ctypes as C
        from ctypes import wintypes as W
        import no_activate
        root = tk.Tk(); root.attributes('-alpha', 0); root.geometry('+20+20')   # shown (sized), not visible
        try:
            ran = []
            button = tk.Button(root, text='単語帳', command=lambda: ran.append(1)); button.pack()
            other = tk.Entry(root); other.pack(); root.update()
            self.assertTrue(no_activate.install(button))
            user = C.WinDLL('user32')
            user.SendMessageW.argtypes = (W.HWND, W.UINT, W.WPARAM, W.LPARAM); user.SendMessageW.restype = C.c_ssize_t
            user.SetFocus.argtypes = (W.HWND,); user.SetFocus.restype = W.HWND
            user.GetFocus.restype = W.HWND
            hwnd = button.winfo_id()
            point = (5 << 16) | 5
            with patch.object(no_activate, 'other_app_in_front', return_value=True):
                user.SetFocus(other.winfo_id())
                user.SendMessageW(hwnd, 0x0201, 1, point)        # WM_LBUTTONDOWN
                self.assertNotEqual(int(user.GetFocus() or 0), hwnd)
                user.SendMessageW(hwnd, 0x0202, 0, point)        # WM_LBUTTONUP
                for _ in range(20):
                    root.update()
                self.assertEqual(ran, [1])
            with patch.object(no_activate, 'other_app_in_front', return_value=False):
                # CorrectNote in front, typing in its text (2026-10-19 うにさん「アプリ内の入力文を
                # フォーカスしているときに単語帳をクリックするとフォーカスが外れて…打てない」):
                # the press does not take the focus either, and the release clicks once
                user.SetFocus(other.winfo_id())
                user.SendMessageW(hwnd, 0x0201, 1, point)
                self.assertEqual(int(user.GetFocus() or 0), other.winfo_id())
                user.SendMessageW(hwnd, 0x0202, 0, point)
                for _ in range(20):
                    root.update()
                self.assertEqual(ran, [1, 1])
                # released outside the button: no click (as a normal button)
                user.SendMessageW(hwnd, 0x0201, 1, point)
                user.SendMessageW(hwnd, 0x0202, 0, (5000 << 16) | 5000)
                for _ in range(20):
                    root.update()
                self.assertEqual(ran, [1, 1])
        finally:
            root.destroy()


def child():
    """A real app in a copied folder; another process's window in front; the word book
    button's command. The front must end up back on the other window."""
    import ctypes as C
    import json
    import subprocess
    import time
    from ctypes import wintypes as W
    from pathlib import Path
    sys.path.insert(0, os.getcwd())
    import app
    import quick_return
    from session import new_tab
    from tests_quick_return import CHILD
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                     encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='')])), encoding='utf8')
    Path('word_book.json').write_text(json.dumps(dict(version=2, sets=[['単語'], [], [], []], active_set=0,
                                                      visible=False, width=200)), encoding='utf8')
    other = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', CHILD.replace("'300x120+700+400'", "'260x90+1000+520'")],
                             stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding='utf-8')
    other_top = int(other.stdout.readline().split()[0])
    root = tk.Tk(); root.withdraw()
    u = quick_return._user(); k = C.WinDLL('kernel32')

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.02)

    def front(target):
        fg = u.GetForegroundWindow(); me = k.GetCurrentThreadId()
        them = u.GetWindowThreadProcessId(fg, None) if fg else 0
        joined = bool(them and them != me and u.AttachThreadInput(me, them, True))
        try:
            u.SetForegroundWindow(target); u.BringWindowToTop(target)
        finally:
            if joined:
                u.AttachThreadInput(me, them, False)
        pump(0.3)
        return int(u.GetForegroundWindow() or 0) == int(target)
    out = {}
    a = None
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
            a = app.CorrectNoteApp(root)
            root.attributes('-alpha', 0)
            pump(1.0)
            out['other_in_front'] = front(other_top)
            if out['other_in_front']:
                a.word_book_btn.invoke()            # the button's command, with the other app in front
                pump(1.0)
                out['book_open'] = a._word_book.window is not None
                out['front_is_other'] = int(u.GetForegroundWindow() or 0) == other_top
                out['remembered_other'] = (getattr(a._word_book._native, 'previous', None) or (0,))[0] == other_top
            print('RESULT ' + json.dumps(out), flush=True)
    finally:
        if a:
            a._on_close()
        else:
            root.destroy()
        other.kill(); other.wait(); other.stdout.close()


@unittest.skipUnless(sys.platform == 'win32', 'Windows activation')
class FromOutsideAppTests(unittest.TestCase):
    def test_word_book_opened_from_outside_leaves_the_other_app_in_front(self):
        import json
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-book-outside-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):
                    shutil.copyfile(path, dest / path.name)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8',
                                 timeout=300)
            line = next((l for l in run.stdout.splitlines() if l.startswith('RESULT ')), None)
            self.assertIsNotNone(line, run.stdout[-3000:])
            r = json.loads(line[7:])
        if not r.get('other_in_front'):
            self.skipTest('this desktop does not let the other window come to the front')
        self.assertTrue(r['book_open'], r)
        self.assertTrue(r['remembered_other'], r)
        self.assertTrue(r['front_is_other'], r)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
