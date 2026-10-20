# -*- coding: utf-8 -*-
"""Windows' restart / shutdown waits for the save (shutdown_guard.py, 2026-10-20 うにさん「保存して
ませんのダイアログで止め、止めると同時に自動保存して、待って閉じたらいいのでは」). With a save
waiting, the question "may the session end?" (WM_QUERYENDSESSION, sent from another thread as
Windows does) is answered "not yet" with the reason 「終了前に自動保存を実行しました。」, the app
saves and closes, and the reason is gone. With nothing waiting, nothing is held. The app test
runs a copy of the folder in a temporary folder and starts it again to see the text come back."""
import json, os, shutil, subprocess, sys, tempfile, threading, time, traceback, unittest
from pathlib import Path
from unittest.mock import Mock, patch

import shutdown_guard

REASON = '終了前に自動保存を実行しました。'


def send_from_another_thread(root, hwnd, msg, wparam=0, lparam=0, seconds=10):
    """SendMessage from a thread of its own (as Windows does); Tk's thread keeps pumping."""
    import ctypes
    u = ctypes.WinDLL('user32')
    u.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                      ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
    answer = []

    def send():
        result = ctypes.c_size_t()
        ok = u.SendMessageTimeoutW(hwnd, msg, wparam, lparam, 0, 8000, ctypes.byref(result))
        answer.append((ok, result.value))
    sender = threading.Thread(target=send)
    sender.start()
    end = time.monotonic() + seconds
    while sender.is_alive() and time.monotonic() < end:
        root.update(); time.sleep(.005)
    sender.join(1)
    return answer[0] if answer else None


def reason_of(hwnd):
    import ctypes
    u = ctypes.WinDLL('user32')
    u.ShutdownBlockReasonQuery.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)]
    size = ctypes.c_uint(256)
    buf = ctypes.create_unicode_buffer(256)
    return buf.value if u.ShutdownBlockReasonQuery(hwnd, buf, ctypes.byref(size)) else None


@unittest.skipUnless(sys.platform == 'win32', 'Windows end of session')
class GuardTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk(); self.root.withdraw()
        self.unsaved = [False]
        self.finished = []
        self.guard = shutdown_guard.ShutdownGuard(self.root, lambda: self.unsaved[0],
                                                  lambda: self.finished.append(reason_of(self.frame)))
        self.assertTrue(self.guard.install())
        end = time.monotonic() + 1
        while time.monotonic() < end:                    # the first look notes Tk's main window
            self.root.update(); time.sleep(.01)
        self.frame = int(self.root.wm_frame(), 16)       # its frame exists once Tk has drawn it
        self.assertEqual(self.guard._frame, self.frame)
        self.assertEqual(self.guard._subclassed, self.frame)   # the main window answers

    def tearDown(self):
        self.guard.close()
        self.root.destroy()

    def test_the_reason_text(self):
        self.assertEqual(shutdown_guard.REASON, REASON)

    def test_nothing_waiting_lets_windows_go_on(self):
        self.assertEqual(send_from_another_thread(self.root, self.frame, 0x0011), (1, 1))
        for _ in range(30):
            self.root.update(); time.sleep(.01)
        self.assertEqual(self.finished, [])
        self.assertIsNone(reason_of(self.frame))

    def test_a_waiting_save_holds_windows_then_saves_and_closes(self):
        self.unsaved[0] = True
        # the hidden window leaves the answer to the main window (listed with its name and icon)
        self.assertEqual(send_from_another_thread(self.root, self.guard.hwnd, 0x0011), (1, 1))
        ok, answer = send_from_another_thread(self.root, self.frame, 0x0011)
        self.assertTrue(ok)
        self.assertEqual(answer, 0)                       # not yet
        for _ in range(60):
            self.root.update(); time.sleep(.01)
            if self.finished:
                break
        # saved and closed while Windows was held, showing this reason on its screen
        self.assertEqual(self.finished, [REASON])
        self.assertIsNone(reason_of(self.frame))          # then let go
        self.assertIsNone(self.guard._job)                # done: no more looking

    def test_forced_end_saves_too(self):
        self.unsaved[0] = True
        send_from_another_thread(self.root, self.frame, 0x0016, 1, 0)    # WM_ENDSESSION(TRUE)
        for _ in range(60):
            self.root.update(); time.sleep(.01)
            if self.finished:
                break
        self.assertEqual(len(self.finished), 1)


def child(step):
    import tkinter as tk
    import app as app_mod
    from session import new_tab
    assert (Path.cwd() / '.ui-test-isolated').exists()
    if step == 'write':
        Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
                                                         input_method_auto=False)), encoding='utf-8')
        Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
            new_tab(text='最初の行です。')])), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); errors = []
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
    with patch.object(app_mod, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app_mod.CorrectNoteApp, '_learn_now', lambda *args: None):
        a = app_mod.CorrectNoteApp(root)
        for _ in range(50):
            root.update(); time.sleep(.01)
        assert not errors, errors
        if step == 'write':
            a.editor.insert('1.end', '\n再起動の直前に書いた行。')
            a._on_change(); root.update()
            assert a._session_after_id, 'a save is waiting'
            guard = a._shutdown_guard
            frame = int(root.wm_frame(), 16)
            assert guard._subclassed == frame, (guard._subclassed, frame)
            # Windows' screen lists the holding window with its title and icon
            import ctypes
            u = ctypes.WinDLL('user32')
            u.SendMessageW.restype = ctypes.c_ssize_t
            u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
            title = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
            u.GetWindowTextW(frame, title, 256)
            assert 'CorrectNote' in title.value, title.value
            u.GetClassLongPtrW.restype = ctypes.c_ssize_t
            u.GetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            icons = [u.SendMessageW(frame, 0x007F, kind, 0) for kind in (0, 1, 2)]   # WM_GETICON
            assert any(icons) or u.GetClassLongPtrW(frame, -14), icons            # GCLP_HICON
            print('TITLE_AND_ICON', flush=True)
            real_close = a._on_close

            def closing():
                print('HELD_AND_SAVED', json.dumps(reason_of(frame), ensure_ascii=False), flush=True)
                real_close()
            a._on_close = closing
            print('SENT %.3f' % time.time(), flush=True)
            ok, answer = send_from_another_thread(root, frame, 0x0011)
            assert ok and answer == 0, (ok, answer)
            end = time.monotonic() + 30
            while time.monotonic() < end:           # the app saves, closes and ends the process
                root.update(); time.sleep(.01)
            raise AssertionError('the process did not end')
        text = a.editor_source_text().rstrip('\n')
        a._on_close()
        assert text == '最初の行です。\n再起動の直前に書いた行。', text
        print('RESTORE_OK', flush=True)


@unittest.skipUnless(sys.platform == 'win32', 'Windows end of session')
class AppTests(unittest.TestCase):
    def test_restart_waits_for_the_save_and_the_text_comes_back(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-shutdown-') as folder:
            dest = Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.ui-test-isolated').touch()
            out = []
            for step in ('write', 'read'):
                log = dest / ('%s.log' % step)
                with open(log, 'w', encoding='utf-8') as f:
                    run = subprocess.run([sys.executable, '-X', 'utf8', str(dest / Path(__file__).name),
                                          '--child', step], cwd=dest, stdout=f, stderr=subprocess.STDOUT,
                                         timeout=300)
                ended = time.time()
                out.append(log.read_text(encoding='utf-8'))
                self.assertEqual(run.returncode, 0, out[-1])
                if step == 'write':
                    sent = float(out[-1].split('SENT ')[1].split()[0])
                    print('from the question to the end of the process: %.2f s' % (ended - sent))
                    # Windows goes on with the restart once the process has gone (aim: about 1 s)
                    self.assertLess(ended - sent, 3.0, out[-1])
            self.assertIn('TITLE_AND_ICON', out[0])
            self.assertIn('HELD_AND_SAVED ' + json.dumps(REASON, ensure_ascii=False), out[0])
            self.assertIn('RESTORE_OK', out[1], out[1])


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[sys.argv.index('--child') + 1])
    else:
        unittest.main()
