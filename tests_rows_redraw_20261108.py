# -*- coding: utf-8 -*-
"""When a few rows get their answers at once (rows coming into view while scrolling), only those rows are drawn again
(2026-11-08, load: the whole correction pane was rebuilt each time). What is drawn is what the whole rebuild draws: the
correction pane's text, its red/green marks, the memo's marks, the row texts and units. An isolated copy, made-up text."""
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
    assert (here / '.ui-rows-redraw-test-isolated').is_file()
    base = ['きょうはあめがふっていたので、かさをもってでかけた', '会議の資料を明日までに作っておく。', 'えきまえのみせでひるごはんをたべた',
            'かいぎのしりょうをあしたまでにつくっておく', '\tタブ\tのある行', 'てがみをかいてポストにいれた', '']
    rows = [base[k % len(base)] for k in range(60)]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='\n'.join(rows))]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if until is not None and until():
                return True
        return False
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+40+40')
        assert pump(120, lambda: a.line_results and a._analyze_pos >= len(a._analyze_todo or ()) and
                    not any(r.get('pending') for r in a.line_results)), 'analysis did not finish'
        pump(1.0)
        real = [dict(r) for r in a.line_results]
        changed_rows = [0, 2, 3, 5, 9, 16]
        assert any(real[i].get('changed') for i in changed_rows), 'made-up rows need some corrections'

        def shown():
            out = dict(result=a.result_view.get('1.0', 'end-1c'), texts=list(a.line_texts), units=repr(a.line_units))
            for w, tags in ((a.editor, ('suspect', 'odd')), (a.result_view, ('fixed', 'chosen'))):
                for t in tags:
                    out[t] = [str(x) for x in w.tag_ranges(t)]
            return out
        got = {}
        for mode in ('1', '0'):
            os.environ['CN_ROWS_REDRAW'] = '1'           # the "before" picture is drawn the same way in both
            for i in changed_rows:
                a.line_results[i] = dict(a._blank_result(rows[i]), pending=True)
            a._refresh_after_analysis(learn=False); pump(0.3)
            for i in changed_rows:
                a.line_results[i] = dict(real[i])
            os.environ['CN_ROWS_REDRAW'] = mode
            calls = []
            real_render = a._render_corrected
            a._render_corrected = lambda *x, **k: (calls.append(1), real_render(*x, **k))[1]
            a._refresh_after_analysis(learn=False); pump(0.3)
            a._render_corrected = real_render
            got[mode] = dict(shown(), full=len(calls))
        assert not errors, errors
        print('ROWS_REDRAW', json.dumps(got, ensure_ascii=False), flush=True)
        a._on_close()


class RowsRedraw(unittest.TestCase):
    def test_same_as_whole_rebuild(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-rows-redraw-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-rows-redraw-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=400)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('ROWS_REDRAW ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('ROWS_REDRAW '):])
            old, new = got['1'], got['0']
            self.assertGreaterEqual(old.pop('full'), 1)       # the old way rebuilt the pane
            self.assertEqual(new.pop('full'), 0)              # the new way drew only the rows
            self.assertEqual(old, new)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
