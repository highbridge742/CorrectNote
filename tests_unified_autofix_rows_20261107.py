# -*- coding: utf-8 -*-
"""The unified view's auto-apply reads the text once and skips rows with no typed mark (2026-11-07, the stop after each
typed row on 2,000 rows). After typing, the note text and every tag of both panes are the same as with the row-by-row
check (_rows_with_typed_marks giving None). An isolated copy of the app, made-up text, both layouts."""
import hashlib
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
    assert (here / '.ui-autofix-test-isolated').is_file()
    layout = sys.argv[sys.argv.index('--child') + 1]
    old_way = sys.argv[sys.argv.index('--child') + 2] == 'rowwise'
    base = ['きょうはあめがふっていた', '会議の資料を明日までに作る。', 'でんしゃがおくれてかいぎにまにあわなかった', '駅前の店で昼ご飯を食べた。']
    text = '\n'.join(base[k % len(base)] + '（%d）' % k for k in range(40))
    (here / 'settings.json').write_text(json.dumps(dict(layout=layout, input_method='kana', input_method_auto=False,
                                                        unified_autofix=True)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if until is not None and until():
                return True
            root.update(); time.sleep(0.005)
        return False
    patches = [patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None),
               patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None)]
    if old_way:
        patches.append(patch.object(app.CorrectNoteApp, '_rows_with_typed_marks', lambda self: None))
    for p in patches:
        p.start()
    a = app.CorrectNoteApp(root)
    root.geometry('900x520+40+40')

    def settled():
        return (not a._foreground_analysis_pending() and getattr(a, '_heavy_redo_job', None) is None
                and not any(r and (r.get('pending') or r.get('deferred_stages')) for r in a.line_results or ()))
    try:
        pump(240, settled); pump(1.5)
        ed = a.editor
        for k, row in enumerate((3, 11, 20)):
            ed.mark_set('insert', '%d.end' % row); ed.focus_force()
            ed.delete('%d.0' % row, '%d.end' % row)
            ed.insert('%d.0' % row, 'あしたのかいぎはじゅうじからでつ', (a.TYPED_TAG,))
            a._on_change()
            pump(2.0); pump(240, settled); pump(1.5)

        def tags(w):
            out = []
            for tag in sorted(w.tag_names()):
                if tag == 'sel':
                    continue
                r = w.tag_ranges(tag)
                if r:
                    out.append((tag, [str(x) for x in r]))
            return out
        dump = repr((ed.get('1.0', 'end-1c'), tags(ed), a.result_view.get('1.0', 'end-1c'), tags(a.result_view)))
        assert not errors, errors
        print('AUTOFIX_FP', hashlib.sha1(dump.encode('utf-8')).hexdigest(), flush=True)
    finally:
        a._on_close()


class UnifiedAutofixRows(unittest.TestCase):
    def run_one(self, layout, way):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-autofix-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-autofix-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child', layout, way],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=600)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('AUTOFIX_FP ')]
            self.assertTrue(line, run.stdout[-3000:])
            return line[0].split()[1]

    def test_unified_same_as_row_by_row(self):
        self.assertEqual(self.run_one('unified', 'skip'), self.run_one('unified', 'rowwise'))

    def test_split_same_as_row_by_row(self):
        self.assertEqual(self.run_one('split', 'skip'), self.run_one('split', 'rowwise'))


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
