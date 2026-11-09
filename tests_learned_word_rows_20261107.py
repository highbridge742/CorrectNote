# -*- coding: utf-8 -*-
"""A word the app learns from what was typed is used by the rows that looked it up (2026-11-07 うにさん「92行目と
95行目が同文ながら一方のみ補正が掛かる」): two identical rows end with the answer a fresh analysis gives, and the
tab is not solved again as a whole. An isolated copy of the app, made-up text, its window kept transparent."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest

ROW = 'でんしゃのしゃそうからみた'
TEACH = '電車の車窓から海が見えた。'      # the app learns 車窓 (しゃそう) from this row
WANT = '電車の車窓からみた'


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    import analysis_worker
    import analysis_work_app as work
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-learned-test-isolated').is_file()
    lines = ['作り物の文書です。', ROW, 'まんなかの行です。', 'もう一行あります。', ROW, '', '']
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                        encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='\n'.join(lines))]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.attributes('-alpha', 0.0)
    clip = []
    root.clipboard_clear = lambda **kw: clip.clear(); root.clipboard_append = lambda t, **kw: clip.append(t)
    root.clipboard_get = lambda **kw: ''.join(clip)
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    passes = []

    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text == a.editor_source_text()
                and a._analyze_pos >= len(a._analyze_todo) and a._analyze_dependencies == analysis_worker.state_key(a)
                and a._analyze_work == work.token(a))

    def settle(limit=200):
        t = time.monotonic()
        while time.monotonic() - t < limit:
            root.update(); time.sleep(0.01)
            if done() and getattr(a, '_heavy_redo_job', None) is None and not any(
                    r and r.get('deferred_stages') for r in (a.line_results or ())):
                break
        e = time.monotonic() + 1.0
        while time.monotonic() < e:
            root.update(); time.sleep(0.01)
        assert not errors, errors

    with patch.object(app, 'GlobalHotkeys', return_value=Mock()):
        try:
            a = app.CorrectNoteApp(root)
            settle()
            assert [a.line_results[i]['corrected'] for i in (1, 4)] == [ROW, ROW], 'the word is already known'
            real = a._trace_analysis
            a._trace_analysis = lambda cause, n, todo, shape: (passes.append((cause, todo, shape)), real(cause, n, todo, shape))
            rev = a.store.revision()
            a.editor.insert('end-1c', TEACH); a._on_change()
            t = time.monotonic()
            while time.monotonic() - t < 30 and a.store.revision() == rev:
                root.update(); time.sleep(0.01)
            assert a.store.revision() != rev, 'nothing was learned'
            settle()
            got = [a.line_results[i]['corrected'] for i in (1, 4)]
            assert got == [WANT, WANT], got
            assert not any(cause == '解き直しの内訳' and '設定や辞書' in str(shape) for cause, todo, shape in passes), passes
            print('LEARNED_WORD_ROWS_PASSED', flush=True)
        finally:
            a._on_close()


class LearnedWordRowsTests(unittest.TestCase):
    def test_both_rows_use_the_learned_word(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-learned-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-learned-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=280)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('LEARNED_WORD_ROWS_PASSED', run.stdout, run.stdout)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
