# -*- coding: utf-8 -*-
"""The whitespace marks read the painted range in one call (2026-11-08, load: one read per row was about 150 Tk calls a
paint). The marks are the same as with one read per row (CN_WS_ROW_GET=1): spaces, full-width spaces, tabs, a tab at
a wrap edge, empty rows, in both panes. An isolated copy, made-up text."""
import json
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
    assert (here / '.ui-ws-one-get-test-isolated').is_file()
    rows = []
    for k in range(120):
        rows.append(['a b  c', '全角　空白　　です', '\tタブ\t\tの行', '', 'x' * 40 + '\t' + 'y' * 70 + '\tz',
                     '終わりの空白  ', ' \t 　 '][k % 7] + (' %d' % k))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                        show_whitespace=True)), encoding='utf-8')
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
        root.geometry('700x500+40+40')
        pump(2.0)
        out = {}

        def marks():
            got = {}
            for w in a._whitespace_targets():
                for t in a.WS_TAGS + (a.WS_NOBOX,):
                    got['%s|%s' % (w.winfo_name(), t)] = [str(x) for x in w.tag_ranges(t)]
            return got
        for top in ('1.0', '40.0', '95.0'):
            a.editor.yview(top); pump(0.3)
            for mode in (True, False):
                a.WS_ROW_GET = mode
                a._ws_paint_sig = {}
                for w in a._whitespace_targets():
                    for t in a.WS_TAGS + (a.WS_NOBOX,):
                        w.tag_remove(t, '1.0', 'end')
                a._paint_whitespace(); pump(0.2)
                a._paint_whitespace(); pump(0.1)
                out['%s|%s' % (top, mode)] = marks()
        assert not errors, errors
        print('WS_ONE_GET', json.dumps(out), flush=True)
        a._on_close()


class WsOneGet(unittest.TestCase):
    def test_same_marks(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-ws-one-get-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-ws-one-get-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('WS_ONE_GET ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('WS_ONE_GET '):])
            for top in ('1.0', '40.0', '95.0'):
                old, new = got['%s|True' % top], got['%s|False' % top]
                self.assertEqual(old, new, top)
                self.assertTrue(any(new.values()), top)        # marks were painted at all


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
