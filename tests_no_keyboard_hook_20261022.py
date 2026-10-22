# -*- coding: utf-8 -*-
"""No PC-wide keyboard hook; brackets on F2 and candidates on F5 (2026-10-22).

うにさん chose to swap the keys so that the bracket key no longer needs the
WH_KEYBOARD_LL hook of native_f5.py (the same shape as a keylogger, a likely
reason for the Store's malware verdict). An owned initial copy starts the app
and quick input in transparent windows that never take focus, records every
SetWindowsHookExW call, and checks the bindings and the Alt+F2 menu guard.
No clipboard, no personal files."""
import json, shutil, subprocess, sys, tempfile, time, traceback, unittest
from pathlib import Path

WH_KEYBOARD, WH_KEYBOARD_LL = 2, 13


def record_hooks():
    """Wrap user32.SetWindowsHookExW for every ctypes library object."""
    import ctypes
    calls = []

    class Recorded:
        def __init__(self, real):object.__setattr__(self, '_real', real)
        def __call__(self, *args):
            calls.append(int(args[0]) if args else None)
            return self._real(*args)
        def __getattr__(self, name):return getattr(self._real, name)
        def __setattr__(self, name, value):setattr(self._real, name, value)

    original = ctypes.CDLL.__getitem__
    def getitem(self, name):
        got = original(self, name)
        if name in ('SetWindowsHookExW', 'SetWindowsHookExA'):return Recorded(got)
        return got
    ctypes.CDLL.__getitem__ = getitem
    return calls


def child():
    calls = record_hooks()
    import tkinter as tk
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    import app, analysis_work_app as work
    from session import new_tab
    assert Path('.no-keyboard-hook-owned').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
        quick_close_clipboard=False, quick_paste_back=False, memory_usage='high')), encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='')])), encoding='utf8')
    root = tk.Tk();root.attributes('-alpha', 0.0);root.withdraw();a = None;errors = []
    root.report_callback_exception = lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def forbid(*args, **kwargs):raise AssertionError('No clipboard access')
    root.clipboard_clear = root.clipboard_append = root.clipboard_get = forbid
    root.tk.eval('rename clipboard {}; proc clipboard {args} {error "No clipboard access"}')
    original_toplevel = tk.Toplevel.__init__
    def transparent(self, *args, **kwargs):
        original_toplevel(self, *args, **kwargs);self.attributes('-alpha', 0.0)
    def until(test, seconds=120):
        end = time.monotonic() + seconds
        while True:
            root.update();assert not errors, errors
            if test():return
            assert time.monotonic() < end, 'timeout'
            time.sleep(.004)
    def bound(widget, sequence):return widget.bind(sequence) or ''
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
             patch.object(app.CorrectNoteApp, '_learn_now', lambda *args:None), \
             patch.object(app.CorrectNoteApp, '_focus_quick_window', lambda *args, **kwargs:None), \
             patch.object(tk.Toplevel, 'winfo_pointerxy', return_value=(300, 200)), \
             patch.object(tk.Toplevel, '__init__', transparent):
            a = app.CorrectNoteApp(root);root.attributes('-alpha', 0.0)
            until(lambda:not a._foreground_analysis_pending() and a._analyze_work == work.token(a))
            a._open_quick_capture();text = a._quick_text
            t0 = time.monotonic();until(lambda:time.monotonic() - t0 > 1)
            assert WH_KEYBOARD_LL not in calls and WH_KEYBOARD not in calls, calls
            assert 'native_f5' not in sys.modules
            assert getattr(a, '_native_f5', None) is None
            assert (a.BRACKET_KEY, a.CANDIDATE_KEY) == ('F2', 'F5')
            for widget in (a.editor, text):
                assert '_on_f5_brackets' in bound(widget, '<F2>'), bound(widget, '<F2>')
                assert '_on_f5_brackets' not in bound(widget, '<F5>'), bound(widget, '<F5>')
            assert '_on_f2_candidates_widget' in bound(a.editor, '<F5>')
            assert '_on_f2_candidates_widget' in bound(a.result_view, '<F5>')
            assert '_on_quick_f2_widget' in bound(text, '<F5>')
            assert '_on_f2_candidates' in (root.bind_class('all', '<F5>') or '')
            assert '_on_f5_brackets' in (root.bind_class('all', '<F2>') or '')
            # Alt+F2: the following Alt-alone menu activation is consumed once.
            text.delete('1.0', 'end');text.insert('1.0', '語');text.tag_add('sel', '1.0', '1.1')
            a._on_f5_brackets(SimpleNamespace(widget=text, keysym='F2', char='', state=0x20000))
            assert text.get('1.0', 'end-1c') == '語（）', text.get('1.0', 'end-1c')   # Alt+F2: at the cursor
            assert a._consume_alt_bracket_menu() and not a._consume_alt_bracket_menu()
            a._on_f5_brackets(SimpleNamespace(widget=text, keysym='F2', char='', state=0x20000))
            a._on_bracket_other_key(SimpleNamespace(keysym='a'))
            assert not a._consume_alt_bracket_menu()
            a._on_f5_brackets(SimpleNamespace(widget=text, keysym='F2', char='', state=0))
            assert not a._consume_alt_bracket_menu()
            text.delete('1.0', 'end');root.update()
            a._close_quick_capture()
            assert WH_KEYBOARD_LL not in calls and WH_KEYBOARD not in calls, calls
            print('NO_KEYBOARD_HOOK_OK hooks=%s' % sorted(set(calls)), flush=True)
    finally:
        if a:
            if getattr(a, '_quick_win', None) is not None:
                a._quick_text.delete('1.0', 'end');a._close_quick_capture()
            a._on_close()
        else:root.destroy()
    assert not errors, errors


class NoKeyboardHookTests(unittest.TestCase):
    def test_app_installs_no_keyboard_hook_and_swaps_keys(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-no-hook-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):shutil.copyfile(path, dest / path.name)
            (dest / '.no-keyboard-hook-owned').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'], cwd=dest,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=240)
            print(run.stdout[-3000:], flush=True)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            self.assertIn('NO_KEYBOARD_HOOK_OK', run.stdout)

    def test_source_no_longer_loads_native_f5(self):
        source = (Path(__file__).resolve().parent / 'app.py').read_text(encoding='utf-8')
        code = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('import native_f5', code);self.assertNotIn('from native_f5', code)
        self.assertNotIn('_start_native_f5', code)


if __name__ == '__main__':child() if '--child' in sys.argv else unittest.main()
