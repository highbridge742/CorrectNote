# -*- coding: utf-8 -*-
"""The scroll record (scroll_trace, 2026-11-07): on by default (うにさん「入れてください」); CN_SCROLL_TRACE=0 or the debug
menu's check (kept for the next start) turns it off, and then nothing is wrapped and no file is made. A move of the note
pane after a right-button release is written with the moving function's name and the seconds since the release, and no
text of the document. An isolated copy of the app, made-up text."""
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
    import scroll_trace
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-scroll-trace-test-isolated').is_file()
    rows = ['%d 行目の作り物のひみつの文です。' % k for k in range(1, 401)]
    extra = json.loads(os.environ.get('TRACE_SETTINGS', '{}'))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False, **extra)),
                                        encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='\n'.join(rows))]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x520+40+40')
        pump(1.5)
        ed = a.editor
        out = dict(on=scroll_trace.enabled(a), wrapped=sorted(k for k in ed.__dict__ if k in ('see', 'yview', 'yview_moveto', 'yview_scroll')))
        ed.event_generate('<ButtonPress-3>', x=200, y=200)
        ed.event_generate('<ButtonRelease-3>', x=200, y=200)
        pump(0.2)
        a._goto_line(300)            # something moves the view after the release
        pump(1.6)                    # the record is written once a second
        path = scroll_trace.log_path(a)
        out['exists'] = os.path.exists(path)
        if out['exists']:
            text = open(path, encoding='utf-8').read()
            records = [json.loads(l) for l in text.splitlines() if l.strip()]
            moves = [r for r in records if r.get('event') == 'move']
            out['moves'] = moves[-3:]
            out['leaks_text'] = any(row in text for row in ('作り物', 'ひみつ', '行目'))
        if scroll_trace.enabled(a):
            scroll_trace.choose(a, False)                # the debug menu's check: off, and kept for the next start
            out['saved_off'] = json.loads((here / 'settings.json').read_text(encoding='utf-8')).get('scroll_trace')
        out['unwrapped'] = not any(k in ed.__dict__ for k in ('see', 'yview', 'yview_moveto', 'yview_scroll'))
        assert not errors, errors
        print('SCROLL_TRACE', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


class ScrollTrace(unittest.TestCase):
    def run_child(self, env_on, settings=None):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-scroll-trace-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-scroll-trace-test-isolated').touch()
            env = dict(os.environ)
            env.pop('CN_SCROLL_TRACE', None)
            env['CN_DEBUG_TOOLS'] = '1'        # the scroll trace is a debug tool from 2026-11-09 (off by default)
            if env_on is not None:
                env['CN_SCROLL_TRACE'] = '1' if env_on else '0'
            env['TRACE_SETTINGS'] = json.dumps(settings or {})
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('SCROLL_TRACE ')]
            self.assertTrue(line, run.stdout[-3000:])
            return json.loads(line[0][len('SCROLL_TRACE '):])

    def test_off_by_the_environment_or_the_saved_check(self):
        for kwargs in (dict(env_on=False), dict(env_on=None, settings=dict(scroll_trace=False))):
            got = self.run_child(**kwargs)
            self.assertFalse(got['on'], (kwargs, got))
            self.assertEqual(got['wrapped'], [], (kwargs, got))
            self.assertFalse(got['exists'], (kwargs, got))

    def test_on_by_default_records_the_mover_after_a_release(self):
        got = self.run_child(None)
        self.assertTrue(got['on'], got)
        self.assertTrue(got['exists'], got)
        self.assertFalse(got['leaks_text'], got)
        moves = got['moves']
        self.assertTrue(moves, got)
        last = moves[-1]
        self.assertTrue(any('_goto_line' in c for c in last['by']['callers']) or
                        any('_center_navigation_line' in c for c in last['by']['callers']), last)
        self.assertIsNotNone(last['since']['right_release'], last)
        self.assertLess(last['since']['right_release'], 10.0, last)
        self.assertTrue(any(m['top_after'] > m['top_before'] for m in moves), moves)
        self.assertTrue(got['unwrapped'], got)
        self.assertIs(got['saved_off'], False, got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
