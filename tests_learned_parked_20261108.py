# -*- coding: utf-8 -*-
"""Leaving a tab before its analysis finishes, automatic learning, coming back (2026-11-08 うにさん「タブ移動したら
全体的に未解析印が付きました」): the rows already read stay; only the rest is read. And automatic learning that
changed nothing (learning is off: vocabulary.LEARNED_OFF) does not move the learning mark at all. An isolated copy,
made-up text."""
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
    import tab_analysis
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-learned-parked-test-isolated').is_file()
    words = ['会議の資料を作る', '明日の予定を確かめる', '駅まで歩いて行く', '新しい本を読んだ', '天気が良いので散歩する']
    long_text = '\n'.join('%s。%d行目の文です。' % (words[i % len(words)], i) for i in range(500))
    tabs = [new_tab(text='短いタブの文。\n二行目。'), new_tab(text=long_text)]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=tabs), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    tk.Misc.clipboard_get = lambda self, **kw: ''
    tk.Misc.clipboard_clear = lambda self, **kw: None
    tk.Misc.clipboard_append = lambda self, s, **kw: None

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
            if until is not None and until():
                return True
        return False
    ready = lambda: sum(1 for r in a.line_results if tab_analysis.reusable_result(r))
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None):
        a = app.CorrectNoteApp(root)
        a._scroll_trace_dir = str(here / 'trace')
        root.deiconify(); pump(5.0)
        a._switch_tab(1)
        pump(20.0, lambda: ready() >= 3)
        out['left_ready'] = ready()
        out['lines'] = len(a.line_results)
        a._switch_tab(0); pump(0.3)
        # automatic learning that changed nothing: no mark moves
        before = app.analysis_async.state_key(a)
        a._learn_english_now('Wonderful Planetarium Notebook keyboard')
        out['nothing_learned_moved'] = [i for i, (x, y) in enumerate(zip(before, app.analysis_async.state_key(a))) if x != y]
        # automatic learning that did learn (what _apply_learned_tokens does when the vocabulary moved)
        a._invalidate_analysis_cache()
        a._retain_finished_rows_after_auto_learning()
        out['learned_moved'] = [i for i, (x, y) in enumerate(zip(before, app.analysis_async.state_key(a))) if x != y]
        pump(0.5)
        a._switch_tab(1); pump(0.1)
        out['back_ready'] = ready()
        out['back_todo'] = len(a._analyze_todo) - a._analyze_pos
        assert not errors, errors[:2]
        print('PARKED', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


class LearnedParked(unittest.TestCase):
    def run_child(self, env):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-learned-parked-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES or entry.name.startswith(
                        ('dict_index.json', 'janome_entries', 'reading_lattice_', 'wlsp_'))):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-learned-parked-test-isolated').touch()
            run = subprocess.run([sys.executable, '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=200, env=dict(os.environ, **env))
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('PARKED ')]
            self.assertTrue(line, run.stdout[-3000:])
            return json.loads(line[0][len('PARKED '):])

    def test_rows_read_before_leaving_stay(self):
        got = self.run_child({})
        print(got)
        self.assertGreaterEqual(got['left_ready'], 3, got)
        self.assertEqual(got['nothing_learned_moved'], [], got)
        self.assertEqual(got['learned_moved'], [3], got)              # only the learning mark
        self.assertGreaterEqual(got['back_ready'], got['left_ready'], got)
        self.assertLess(got['back_todo'], got['lines'], got)

    def test_old_form_reads_everything_again(self):
        got = self.run_child({'CN_LEARNED_PARKED': '0', 'CN_LEARN_REV_CHECK': '0'})
        print(got)
        self.assertEqual(got['back_ready'], 0, got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
