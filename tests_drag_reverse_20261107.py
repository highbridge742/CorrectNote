# -*- coding: utf-8 -*-
"""A right drag does not jump about 30 rows the other way in one step (2026-11-07 うにさん「右ドラッグを離すと元の行に
戻る」: the record showed, right after reaching row 1, one step of the same drag going back down about 30 rows; a move
back of the hidden cursor counted as the hand's). Ordinary steps both ways still scroll. An isolated copy, made-up text,
the pointer position scripted (the real cursor is not moved)."""
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
    assert (here / '.ui-drag-reverse-test-isolated').is_file()
    rows = ['%d 行目の作り物の文です。' % k for k in range(1, 401)]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                        right_drag_inertia=False)), encoding='utf-8')
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
        a._edge_warp = lambda d, widget, event: None
        pointer = [300]
        pointer_x = [300]
        ed.winfo_pointery = lambda: ed.winfo_rooty() + pointer[0]
        ed.winfo_pointerx = lambda: ed.winfo_rootx() + pointer_x[0]
        warps = []
        def warp(widget, x, y):
            warps.append((x, y)); pointer_x[0] = x; pointer[0] = y
            return 'sync'
        a._warp_pointer = warp
        ed.yview('12.0'); pump(0.3)
        out = {}
        ed.event_generate('<ButtonPress-3>', x=300, y=300)
        pump(0.05)
        tops = []
        # move the hand down (toward row 1) in 40 px steps, then one step of -900 px (the cursor put back), then on
        for step in [40] * 12 + [-900] + [40] * 3:
            pointer[0] += step
            ed.event_generate('<B3-Motion>', x=300, y=max(0, min(599, pointer[0])), state=0x400)
            pump(0.02)
            tops.append(int(ed.index('@0,0').split('.')[0]))
        ed.event_generate('<ButtonRelease-3>', x=300, y=300, state=0x400)
        pump(0.3)
        out['tops'] = tops
        # ordinary drags still scroll both ways
        ed.yview('100.0'); pump(0.3)
        ed.event_generate('<ButtonPress-3>', x=300, y=300); pump(0.05)
        pointer[0] = 300
        for step in [-40] * 6 + [40] * 3:
            pointer[0] += step
            ed.event_generate('<B3-Motion>', x=300, y=max(0, min(599, pointer[0])), state=0x400)
            pump(0.02)
        out['after_both_ways'] = int(ed.index('@0,0').split('.')[0])
        ed.event_generate('<ButtonRelease-3>', x=300, y=300, state=0x400)
        pump(0.3)
        # うにさんの形（22:51）: 下から上へ、右ドラッグを何度も繰り返す。途中でカーソルが欄の横（隣の低い画面）へ出て、
        # 縦が約500px 上へ寄せられる歩が混じる。最後（1行目）まで送れること
        ed.yview('380.0'); pump(0.3)
        for k in range(30):
            pointer[0] = 150; pointer_x[0] = 300
            ed.event_generate('<ButtonPress-3>', x=300, y=150); pump(0.03)
            for j in range(10):
                if j == 3:
                    pointer_x[0] = -40; pointer[0] -= 500        # into the next screen, pulled up to its bottom
                elif pointer_x[0] >= 0:
                    pointer[0] += 40
                # else: the cursor sits at the bottom of the lower screen and cannot go further down
                ed.event_generate('<B3-Motion>', x=300, y=max(0, min(599, pointer[0])), state=0x400)
                pump(0.015)
            ed.event_generate('<ButtonRelease-3>', x=300, y=150, state=0x400); pump(0.05)
            if int(ed.index('@0,0').split('.')[0]) == 1:
                break
        out['repeated_to_top'] = int(ed.index('@0,0').split('.')[0])
        out['drags'] = k + 1
        assert not errors, errors
        print('DRAG_REVERSE', json.dumps(out), flush=True)
        a._on_close()


class DragReverse(unittest.TestCase):
    def test_no_reverse_jump(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-drag-reverse-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-drag-reverse-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('DRAG_REVERSE ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('DRAG_REVERSE '):])
            tops = got['tops']
            self.assertEqual(tops[11], 1, got)                    # the drag reached row 1
            self.assertLessEqual(tops[12], 3, got)                # the -900 px step: no jump back down
            self.assertGreater(got['after_both_ways'], 100, got)  # ordinary steps still scroll (hand up 6, down 3)
            self.assertEqual(got['repeated_to_top'], 1, got)      # repeated drags reach the first row


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
