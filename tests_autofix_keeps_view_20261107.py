# -*- coding: utf-8 -*-
"""The unified view's auto-apply does not pull the view back to the cursor's row when the cursor was out of view
(2026-11-07, うにさん「右ドラッグを離すと元の行に戻る」: an answer arriving later auto-applied the typed row and
see('insert') scrolled back to it). With the cursor in view it is still kept in view. An isolated copy, made-up text."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
import unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-autofix-view-test-isolated').is_file()
    rows = ['%d 行目の作り物の文です。' % k for k in range(1, 401)]
    (here / 'settings.json').write_text(json.dumps(dict(layout='unified', input_method='kana', input_method_auto=False,
                                                        unified_autofix=True)), encoding='utf-8')
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
        pump(2.0)
        ed = a.editor
        typed_row = 30
        typed = 'あしたのかいぎ%d' % typed_row
        fixed = 'あしたの会議%d' % typed_row

        def answer_arrives():
            # the row was typed; its answer (an auto-applied correction) arrives now
            ed.delete(f'{typed_row}.0', f'{typed_row}.end'); ed.insert(f'{typed_row}.0', typed)
            ed.mark_set('insert', f'{typed_row}.end')
            lines = ed.get('1.0', 'end-1c').split('\n')
            a.line_results = [dict(original=t, corrected=(fixed if i == typed_row - 1 else t), pending=False,
                                   changed=(i == typed_row - 1)) for i, t in enumerate(lines)]
            a.unified_autofix_on = lambda: True
            a._autofix_live_records = lambda *x: []
            a._change_is_inside_typed = lambda *x: True
            a._restore_typed_ranges = Mock(); a._autofix_remember = Mock(); a._repaint_autofix_tags = Mock()
            a._units_cache = {}
            a._analyze_dependencies = None
            with patch.object(app, 'build_line_units', side_effect=lambda r, *x: (r['corrected'], [])):
                applied = a._apply_unified_autofix()
            assert applied, 'nothing applied'
            assert ed.get(f'{typed_row}.0', f'{typed_row}.end') == fixed
        out = {}
        # 1) scrolled away (a right drag after typing): the view stays
        ed.see(f'{typed_row}.0'); pump(0.2)
        ed.yview(f'{typed_row + 150}.0'); pump(0.2)
        top_before = ed.index('@0,0')
        answer_arrives(); pump(0.3)
        out['away'] = (top_before, ed.index('@0,0'), ed.bbox('insert') is not None)
        # 2) the cursor in view (typing): it stays in view
        ed.yview(f'{typed_row - 5}.0'); pump(0.2)
        answer_arrives(); pump(0.3)
        out['typing'] = ed.bbox('insert') is not None
        assert not errors, errors
        print('AUTOFIX_VIEW', json.dumps(out), flush=True)
        a._on_close()


class AutofixKeepsView(unittest.TestCase):
    def test_view_stays_when_the_cursor_was_out_of_view(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-autofix-view-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-autofix-view-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('AUTOFIX_VIEW ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('AUTOFIX_VIEW '):])
            before, after, seen = got['away']
            self.assertEqual(before, after, got)        # not pulled back to the typed row
            self.assertFalse(seen, got)
            self.assertTrue(got['typing'], got)         # typing: the cursor stays in view


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
