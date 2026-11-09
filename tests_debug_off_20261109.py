# -*- coding: utf-8 -*-
"""The debug menu and the measuring are off by default (2026-11-09 うにさん「スクロールは解決しているようなので、
デバッグメニューや計測を外してください」): no デバッグメニュー… in the about menu, nothing written to scroll_trace or
while scrolling, and the saved debug_timings still take effect. CN_DEBUG_TOOLS=1 brings
them back. An isolated copy, made-up text."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-debug-off-test-isolated').is_file()
    text = '\n'.join('%d行目の文です。' % i for i in range(300))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                        debug_timings=dict(tab_wheel_same=68))), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    tk.Misc.clipboard_get = lambda self, **kw: ''
    tk.Misc.clipboard_clear = lambda self, **kw: None
    tk.Misc.clipboard_append = lambda self, s, **kw: None

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    labels = []
    real_add = tk.Menu.add_command

    def add_command(self, cnf=None, **kw):
        labels.append(kw.get('label'))
        return real_add(self, cnf, **kw)
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None), patch.object(tk.Menu, 'add_command', add_command):
        a = app.CorrectNoteApp(root)
        pump(1.0)
        out['menu_item'] = 'デバッグメニュー…' in labels
        out['same_ms'] = a.TAB_WHEEL_SAME_MS
        for _ in range(5):
            a.editor.yview_scroll(10, 'units'); pump(0.1)
        a.editor.yview_moveto(0.0); pump(0.3)
        out['trace_on'] = bool((getattr(a, '_scroll_trace', None) or {}).get('on'))
        # the debug window: its items are there, the scroll-record item is not (2026-11-09 うにさん)
        dlg = a.open_debug_menu() or getattr(a, '_debug_window', None)
        pump(0.3)
        texts = []
        stack = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        while stack:
            w = stack.pop()
            try:
                texts.append(str(w.cget('text')))
            except Exception:
                pass
            stack.extend(w.winfo_children())
        out['debug_scroll_item'] = any('スクロールの記録' in t for t in texts)
        out['debug_items'] = any('解析の記録' in t for t in texts)
        assert not errors, errors[:2]
        a._on_close()
    folder = here / 'tools_local' / 'scroll_trace'
    out['trace_files'] = sorted(p.name for p in folder.iterdir()) if folder.exists() else []
    out['usage_file'] = (here / 'usage_counts.json').exists()
    print('DEBUG_OFF', json.dumps(out, ensure_ascii=False), flush=True)


class DebugOff(unittest.TestCase):
    def run_child(self, env):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-debug-off-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-debug-off-test-isolated').touch()
            full = dict(os.environ)
            for name in ('CN_DEBUG_TOOLS', 'CN_SCROLL_TRACE', 'CN_REDO_TRACE'):
                full.pop(name, None)
            full.update(env)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, env=full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=200)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('DEBUG_OFF ')]
            self.assertTrue(line, run.stdout[-3000:])
            return json.loads(line[0][len('DEBUG_OFF '):])

    def test_off_by_default(self):
        got = self.run_child({})
        print(got)
        self.assertTrue(got['menu_item'], got)                    # the debug menu stays (2026-11-09 うにさん)
        self.assertFalse(got['trace_on'], got)
        self.assertFalse(got['debug_scroll_item'], got)
        self.assertFalse(got['debug_items'], got)                 # 解析の記録… also taken off for now (2026-11-09)
        self.assertEqual(got['trace_files'], [], got)
        self.assertEqual(got['same_ms'], 68, got)               # the saved debug_timings still work

    def test_usage_counts_stay_unless_switched_off(self):
        # the usage counts are kept for the long term (2026-10-24): read and written as before; CN_USAGE_COUNTS=0 stops
        # them. Whether a file appears depends on the steps having counted something, so check the switch directly
        import importlib, sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        import app
        written = []
        fake = type('F', (), {})()
        from unittest import mock
        with mock.patch('usage_counts.snapshot', return_value={'_stage': [1, 0]}), \
                mock.patch.object(app, 'USAGE_COUNTS_FILE', os.path.join(tempfile.mkdtemp(), 'usage_counts.json')):
            with mock.patch.dict(os.environ, {'CN_USAGE_COUNTS': '0'}):
                app.CorrectNoteApp._save_usage_counts(fake)
                written.append(os.path.exists(app.USAGE_COUNTS_FILE))
            os.environ.pop('CN_USAGE_COUNTS', None)
            app.CorrectNoteApp._save_usage_counts(fake)
            written.append(os.path.exists(app.USAGE_COUNTS_FILE))
        self.assertEqual(written, [False, True])

    def test_back_with_the_switch(self):
        got = self.run_child({'CN_DEBUG_TOOLS': '1'})
        print(got)
        self.assertTrue(got['menu_item'], got)
        self.assertTrue(got['trace_on'], got)
        self.assertTrue(got['debug_scroll_item'], got)
        self.assertTrue(got['debug_items'], got)
        self.assertEqual(got['same_ms'], 68, got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
