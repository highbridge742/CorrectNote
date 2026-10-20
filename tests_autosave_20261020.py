# -*- coding: utf-8 -*-
"""Saves are gathered every 5 minutes (2026-10-20 うにさん「手動でアプリを落とした時や、PCの
正常なシャットダウンの時に、記録を残して次回続きから」; first 30 s, then 5 min): the session and
the vocabulary are written once, AUTOSAVE_MS after the first change (typing on does not put it
off), an unchanged session is not written again, closing a tab saves at once, and Windows'
end-of-session notice (WM_QUERYENDSESSION, which Tk hands on as WM_SAVE_YOURSELF) saves the
text so the next start goes on from it. Files are written in temporary folders only."""
import json, os, shutil, subprocess, sys, tempfile, time, traceback, unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
import session as session_mod


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.next = 0

    def after(self, ms, func):
        self.next += 1
        self.jobs['job%d' % self.next] = (ms, func)
        return 'job%d' % self.next

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run(self, job):
        ms, func = self.jobs.pop(job)
        func()


def bare_app():
    a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
    a.root = FakeRoot()
    a._session_after_id = None
    a._save_session = Mock()
    a.store = Mock()
    return a


class ConsoleHandlerTests(unittest.TestCase):
    def setUp(self):
        import threading
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root = FakeRoot()
        self.a._has_console = lambda: True
        self.ended = []
        self.a._on_windows_session_end = lambda: self.ended.append(threading.current_thread().name)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows console')
    def test_only_close_logoff_and_shutdown_wait_for_the_save(self):
        import ctypes
        a = self.a
        a._install_console_close_save()
        try:
            (job, (ms, watch)), = a.root.jobs.items()
            self.assertEqual(ms, 200)
            self.assertEqual(a._console_handler(0), 0)       # Ctrl+C: as before
            self.assertEqual(a._console_handler(1), 0)       # Ctrl+Break: as before
            self.assertFalse(a._console_end.is_set())
            a.root.run(job)                                  # nothing to do yet: looks again later
            self.assertEqual(self.ended, [])
            (job, (ms, watch)), = a.root.jobs.items()
            a.CONSOLE_CLOSE_WAIT_S = 0.05                    # nobody saves in time: gives up after the wait
            start = time.monotonic()
            self.assertEqual(a._console_handler(2), 1)
            self.assertGreaterEqual(time.monotonic() - start, 0.04)
            a.root.run(job)                                  # the main thread saves, then stops looking
            self.assertEqual(self.ended, ['MainThread'])
            self.assertEqual(a.root.jobs, {})
            self.assertTrue(a._console_saved.is_set())
        finally:
            kernel = ctypes.WinDLL('kernel32')
            kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, ctypes.c_int]
            kernel.SetConsoleCtrlHandler(a._console_handler, 0)

    def test_without_a_console_nothing_is_installed(self):
        a = self.a
        a._has_console = lambda: False
        a._install_console_close_save()
        self.assertIsNone(getattr(a, '_console_handler', None))
        self.assertEqual(a.root.jobs, {})


class IntervalTests(unittest.TestCase):
    def test_interval_is_5_minutes(self):
        self.assertEqual(app.AUTOSAVE_MS, 300000)

    def test_session_save_is_not_put_off_by_more_typing(self):
        a = bare_app()
        for _ in range(5):
            app.CorrectNoteApp._schedule_session_save(a)
        self.assertEqual(len(a.root.jobs), 1)
        (job, (ms, func)), = a.root.jobs.items()
        self.assertEqual(ms, 300000)
        self.assertEqual(a._session_after_id, job)
        func()
        a._save_session.assert_called_once_with()

    def test_vocabulary_saves_are_gathered(self):
        a = bare_app()
        for _ in range(4):
            app.CorrectNoteApp._schedule_store_save(a)
        self.assertEqual(len(a.root.jobs), 1)
        a.store.save_in_background.assert_not_called()
        job = a._store_save_after_id
        self.assertEqual(a.root.jobs[job][0], 300000)
        a.root.run(job)
        a.store.save_in_background.assert_called_once_with()
        self.assertIsNone(a._store_save_after_id)
        app.CorrectNoteApp._schedule_store_save(a)      # a later change gets a new one
        self.assertEqual(len(a.root.jobs), 1)

    def test_without_a_window_the_vocabulary_is_written_at_once(self):
        a = bare_app(); a.root = None
        app.CorrectNoteApp._schedule_store_save(a)
        a.store.save_in_background.assert_called_once_with()

    def test_windows_session_end_saves_everything_at_once(self):
        a = bare_app()
        calls = []
        a._design33_flush = lambda: calls.append('flush')
        a._save_session = lambda: calls.append('session')
        a.store.save = lambda: calls.append('vocabulary')
        a._save_analysis_cache = lambda: calls.append('analysis')
        app.CorrectNoteApp._schedule_session_save(a)
        app.CorrectNoteApp._schedule_store_save(a)
        app.CorrectNoteApp._on_windows_session_end(a)
        self.assertEqual(calls, ['flush', 'session', 'vocabulary', 'analysis'])
        self.assertEqual(a.root.jobs, {})               # nothing left to write twice later
        a.store.save_in_background.assert_not_called()

    def test_closing_a_tab_and_the_app_save_at_once(self):
        import inspect
        close_tab = inspect.getsource(app.CorrectNoteApp._close_tab)
        self.assertIn('self._save_session()', close_tab)
        self.assertNotIn('self._schedule_session_save()', close_tab)
        on_close = inspect.getsource(app.CorrectNoteApp._on_close)
        self.assertIn('self._cancel_store_save()', on_close)
        self.assertLess(on_close.index('self._save_session()'), on_close.index('self.store.save()'))


class SessionFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='correctnote-autosave-')
        self.path = os.path.join(self.folder, 'session.json')

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_unchanged_session_is_not_written_again(self):
        s = session_mod.SessionStore(self.path)
        s.tabs = [session_mod.new_tab(text='本文です。')]
        writes = []
        real = os.replace

        def counting(src, dst):
            writes.append(dst)
            return real(src, dst)
        with patch.object(session_mod.os, 'replace', counting):
            self.assertTrue(s.save())
            self.assertTrue(s.save())
            self.assertEqual(len(writes), 1)
            s.tabs[0]['text'] = '本文です。追記'
            self.assertTrue(s.save())
            self.assertEqual(len(writes), 2)
            os.remove(self.path)                        # gone: written again
            self.assertTrue(s.save())
            self.assertEqual(len(writes), 3)
        with open(self.path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertNotIn('saved_at', data)              # no time of saving is kept
        self.assertEqual(data['tabs'][0]['text'], '本文です。追記')
        self.assertFalse(os.path.exists(self.path + '.tmp'))


@unittest.skipUnless(sys.platform == 'win32', 'Windows end-of-session message')
class WindowsMessageTests(unittest.TestCase):
    def test_query_end_session_reaches_wm_save_yourself(self):
        import ctypes
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        try:
            got = []
            root.protocol('WM_SAVE_YOURSELF', lambda: got.append(True))
            root.update()
            frame = int(root.wm_frame(), 16)
            # Posted, so it arrives through Tk's own message loop as Windows' does (a SendMessage
            # from ctypes would run Tk's handler without the GIL)
            u = ctypes.WinDLL('user32')
            u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
            self.assertTrue(u.PostMessageW(frame, 0x0011, 0, 0))     # WM_QUERYENDSESSION
            for _ in range(50):
                root.update()
                if got:
                    break
                time.sleep(.01)
            self.assertEqual(got, [True])
        finally:
            root.destroy()


def child(step):
    import tkinter as tk
    import app as app_mod
    from session import new_tab
    assert (Path.cwd() / '.ui-test-isolated').exists()
    if step.startswith('write'):
        Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
                                                         input_method_auto=False)), encoding='utf-8')
        Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
            new_tab(text='最初の行です。')])), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); errors = []
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
    with patch.object(app_mod, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app_mod.CorrectNoteApp, '_learn_now', lambda *args: None), \
            patch.object(app_mod.CorrectNoteApp, '_has_console', staticmethod(lambda: step == 'write-console')):
        a = app_mod.CorrectNoteApp(root)
        for _ in range(50):
            root.update(); time.sleep(.01)
        assert not errors, errors
        if step == 'write-console':
            # Started from py.exe / python.exe: Windows closes the console when it restarts, and
            # calls the console handler on a thread of its own (CTRL_CLOSE_EVENT = 2)
            a.editor.insert('1.end', '\n続きの行を書きました。')
            a._on_change(); root.update()
            assert a._session_after_id, 'a save is waiting'
            import threading
            answer = []
            caller = threading.Thread(target=lambda: answer.append(a._console_handler(2)))
            started = time.monotonic()
            caller.start()
            while caller.is_alive() and time.monotonic() - started < 10:
                root.update(); time.sleep(.01)
            assert answer == [1], answer
            assert time.monotonic() - started < a.CONSOLE_CLOSE_WAIT_S, 'it waited for the save, not the time limit'
            assert not a._session_after_id, 'saved at once, nothing left waiting'
            print('SAVED', flush=True)
            import analysis_async, multiprocessing
            analysis_async.close(a)
            for worker in multiprocessing.active_children():
                worker.terminate()
            os._exit(0)                                 # then Windows ends the process
        if step == 'write':
            a.editor.insert('1.end', '\n続きの行を書きました。')
            a._on_change(); root.update()
            assert a._session_after_id, 'a save is waiting'
            # Windows asks whether it may end the session: Tk calls WM_SAVE_YOURSELF
            import ctypes
            u = ctypes.WinDLL('user32')
            u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
            # This checks the fallback (Tk's WM_SAVE_YOURSELF): the shutdown guard, which holds
            # Windows and closes the app itself, is tested in tests_shutdown_guard_20261020
            a._shutdown_guard.close()
            ended = []
            real_end = a._on_windows_session_end
            a._on_windows_session_end = lambda: (real_end(), ended.append(True))
            root.protocol('WM_SAVE_YOURSELF', a._on_windows_session_end)
            assert u.PostMessageW(int(root.wm_frame(), 16), 0x0011, 0, 0)
            for _ in range(200):
                root.update()
                if ended:
                    break
                time.sleep(.01)
            assert ended, 'WM_SAVE_YOURSELF did not arrive'
            assert not a._session_after_id, 'saved at once, nothing left waiting'
            print('SAVED', flush=True)
            # Then Windows ends the process: no _on_close. Only the analysis workers are
            # stopped here, as Windows would stop them too.
            import analysis_async, multiprocessing
            analysis_async.close(a)
            for worker in multiprocessing.active_children():
                worker.terminate()
            os._exit(0)
        text = a.editor_source_text().rstrip('\n')
        print('RESTORED', json.dumps(text, ensure_ascii=False), flush=True)
        a._on_close()
        assert text == '最初の行です。\n続きの行を書きました。', text
        print('RESTORE_OK', flush=True)


@unittest.skipUnless(sys.platform == 'win32', 'Windows end-of-session message')
class RestartTests(unittest.TestCase):
    def test_text_written_before_shutdown_comes_back(self):
        self.restart('write')

    def test_text_written_before_the_console_is_closed_comes_back(self):
        self.restart('write-console')

    def restart(self, first):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-autosave-') as folder:
            dest = Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.ui-test-isolated').touch()
            out = []
            for step in (first, 'read'):
                log = dest / ('%s.log' % step)      # a file, not a pipe a stray process could hold
                with open(log, 'w', encoding='utf-8') as f:
                    run = subprocess.run([sys.executable, '-X', 'utf8', str(dest / Path(__file__).name),
                                          '--child', step], cwd=dest, stdout=f, stderr=subprocess.STDOUT,
                                         timeout=300)
                out.append(log.read_text(encoding='utf-8'))
                self.assertEqual(run.returncode, 0, out[-1])
            self.assertIn('SAVED', out[0])
            self.assertIn('RESTORE_OK', out[1], out[1])


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[sys.argv.index('--child') + 1])
    else:
        unittest.main()
