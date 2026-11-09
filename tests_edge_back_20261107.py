# -*- coding: utf-8 -*-
"""Ctrl+End twice comes back to where the cursor was (2026-11-07 うにさん「Ctrl+Endで最下に移動した後、Ctrl+Endしても
途中の行に戻りませんでした」): the last row is centred, and that centring and its release at the next key moved the top
row, which counted as a move. A scroll by the user still forgets the way back. An isolated copy, made-up text."""
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
    assert (here / '.ui-edge-back-test-isolated').is_file()
    rows = [('%d 行目の作り物の文です。' % k) * (1 + k % 7) for k in range(1, 401)]      # some rows wrap
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
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
        root.geometry('900x600+40+40')
        pump(1.5)
        ed = a.editor
        out = {}

        def press_end():
            a._release_navigation_padding()        # what the next key does first (_release_native_navigation)
            a._goto_document_edge(True)
            pump(0.6)
        ed.mark_set('insert', '120.3'); ed.see('insert'); pump(0.3)
        press_end()
        out['first'] = ed.index('insert'); out['top_after_first'] = ed.index('@0,0')
        press_end()
        out['second'] = ed.index('insert')
        # a wheel scroll after the jump: the next Ctrl+End goes to the end again (not back)
        ed.mark_set('insert', '150.0'); ed.see('insert'); pump(0.3)
        press_end()
        a._on_wheel_units(-12); pump(0.3)
        press_end()
        out['after_scroll'] = ed.index('insert')
        assert not errors, errors
        print('EDGE_BACK', json.dumps(out), flush=True)
        a._on_close()


class EdgeBack(unittest.TestCase):
    def test_ctrl_end_twice_comes_back(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-edge-back-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-edge-back-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('EDGE_BACK ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('EDGE_BACK '):])
            self.assertGreaterEqual(int(got['first'].split('.')[0]), 400, got)      # the last row
            self.assertEqual(got['second'], '120.3', got)
            self.assertGreaterEqual(int(got['after_scroll'].split('.')[0]), 400, got)


class FollowOwnMove(unittest.TestCase):
    """The case from うにさん's record (22:27): Ctrl+End centred the last row with its top at 3688; the next press first
    released the centring margin (_release_navigation_padding), moving the top to 3686, and the way back was forgotten."""
    def test_the_release_of_the_margin_keeps_the_way_back(self):
        from types import SimpleNamespace
        import app
        a = SimpleNamespace(editor=SimpleNamespace(index=lambda i: '3686.0'),
                            _edge_back=dict(stamp=(True, 'tab', 1, '3713.0', '3688'), insert='120.3', top='110.0'))
        app.CorrectNoteApp._edge_follow_own_move(a, '3688')
        self.assertEqual(a._edge_back['stamp'][-1], '3686')
        # a move the app did not make itself (another top): the way back is not touched here
        a._edge_back['stamp'] = (True, 'tab', 1, '3713.0', '3600')
        app.CorrectNoteApp._edge_follow_own_move(a, '3688')
        self.assertEqual(a._edge_back['stamp'][-1], '3600')


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
