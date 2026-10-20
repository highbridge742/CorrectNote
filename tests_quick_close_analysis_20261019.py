# -*- coding: utf-8 -*-
"""Analysis runs after quick input sends its text, with no click on CorrectNote.

2026-10-19 うにさん: another window in front, CorrectNote behind; the row numbers kept
showing "not analysed", and only a click on CorrectNote started the analysis (from 1).
Quick input had been used often. Here an isolated app, never brought to the front, opens
quick input, types, closes it (its text goes into the memo) several times, and the memo's
analysis must finish within a time limit without any further event."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch


def child(case):
    import tkinter as tk
    sys.path.insert(0, os.getcwd())
    import app
    import analysis_work_app
    import analysis_worker
    import quick_return
    from session import new_tab
    Path('.ui-test-isolated').write_text('', encoding='utf8')
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
                                                     input_method_auto=False, quick_paste_back=True,
                                                     show_ctrl_boundaries=(case == 'stale_ime'))),
                                     encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        new_tab(text='きょうはいい天気です。\nあしたもはれるでしょう。')])), encoding='utf8')
    root = tk.Tk()
    root.withdraw()
    root.attributes('-alpha', 0)
    root.clipboard_clear = lambda *a, **k: None
    root.clipboard_append = lambda *a, **k: None
    a = None

    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text == a.editor_source_text()
                and a._analyze_pos >= len(a._analyze_todo)
                and a._analyze_dependencies == analysis_worker.state_key(a)
                and a._analyze_work == analysis_work_app.token(a))

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            if until is not None and until():
                return True
            time.sleep(0.01)
        return until() if until is not None else None

    out = dict(rounds=[])
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None), \
                patch.object(tk.Toplevel, 'winfo_pointerxy', return_value=(300, 200)), \
                patch.object(quick_return, 'restore', lambda target, root_, paste=False: case == 'back'):
            a = app.CorrectNoteApp(root)
            out['startup_done'] = pump(120, done)
            if case == 'stale_ime':
                # A conversion left unconfirmed in the memo when the focus went elsewhere
                # (the IME keeps it in the memo's context while the window has no focus).
                out['composition_set'] = set_composition(a.editor.winfo_id(), 'へんかんちゅう')
            for round_ in range(4 if case != 'stale_ime' else 1):
                a._open_quick_capture()
                pump(0.3)
                for ch in 'かんいにゅうりょくのぶん':
                    a._quick_text.insert('insert', ch)
                    a._quick_text.event_generate('<<Modified>>')
                    pump(0.03)
                pump(0.6)                 # let quick input's own analysis run
                if case == 'back':
                    a._quick_return = quick_return.Target(1, 2, 3, 4, True)
                a._close_quick_capture()
                started = time.monotonic()
                finished = pump(20, done)
                out['rounds'].append(dict(done=finished, seconds=round(time.monotonic() - started, 2),
                                          todo=len(a._analyze_todo), pos=a._analyze_pos,
                                          same_text=a._analyze_text == a.editor_source_text(),
                                          pending=a._foreground_analysis_pending(),
                                          after_id=a._after_id is not None,
                                          job=a._analyze_job is not None,
                                          warming=getattr(a, '_tab_warming', False),
                                          warmup=getattr(a, '_warmup', None) is not None,
                                          scope=getattr(a, '_async_context_scope', None) is not None,
                                          speculation=getattr(a, '_ime_speculation', None) is not None,
                                          view=a._view_changing()))
            if case == 'stale_ime':
                # The rows' "not analysed" marks (the line numbers) must clear as well
                rows = len(a.editor_source_text().split('\n'))
                states = lambda: [a._line_analysis_display_state(r) for r in range(1, rows + 1)
                                  if a.editor.get(f'{r}.0', f'{r}.end').strip()]
                out['marks_cleared'] = pump(20, lambda: all(s == 'done' for s in states()))
                out['row_states'] = states()
                import ime_watch
                out['still_composing'] = ime_watch.composition_active(a.editor.winfo_id())
                out['boundary_on'] = getattr(a.editor, '_correctnote_boundary_colors', None) is not None
                cancel_composition(a.editor.winfo_id())
            print('RESULT ' + json.dumps(out, ensure_ascii=False, default=str), flush=True)
    finally:
        if a:
            a._on_close()
        else:
            root.destroy()


def _imm():
    import ctypes as C
    from ctypes import wintypes as W
    imm = C.WinDLL('imm32')
    imm.ImmGetContext.argtypes = (W.HWND,); imm.ImmGetContext.restype = W.HANDLE
    imm.ImmReleaseContext.argtypes = (W.HWND, W.HANDLE)
    imm.ImmSetOpenStatus.argtypes = (W.HANDLE, W.BOOL)
    imm.ImmSetCompositionStringW.argtypes = (W.HANDLE, W.DWORD, C.c_wchar_p, W.DWORD, C.c_void_p, W.DWORD)
    imm.ImmSetCompositionStringW.restype = W.BOOL
    imm.ImmNotifyIME.argtypes = (W.HANDLE, W.DWORD, W.DWORD, W.DWORD)
    return imm


def set_composition(hwnd, text):
    """Our own memo's IME context only (the test app's window)."""
    imm = _imm()
    himc = imm.ImmGetContext(hwnd)
    if not himc:
        return False
    try:
        imm.ImmSetOpenStatus(himc, True)
        return bool(imm.ImmSetCompositionStringW(himc, 0x0009, text, len(text) * 2, None, 0))   # SCS_SETSTR
    finally:
        imm.ImmReleaseContext(hwnd, himc)


def cancel_composition(hwnd):
    imm = _imm()
    himc = imm.ImmGetContext(hwnd)
    if himc:
        imm.ImmNotifyIME(himc, 0x0015, 0x0004, 0)      # NI_COMPOSITIONSTR, CPS_CANCEL
        imm.ImmSetOpenStatus(himc, False)
        imm.ImmReleaseContext(hwnd, himc)


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class QuickCloseAnalysisTests(unittest.TestCase):
    def run_case(self, case):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-quick-analysis-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):
                    shutil.copyfile(path, dest / path.name)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name),
                                  '--child', case], cwd=dest, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, encoding='utf8', timeout=400)
            line = next((l for l in run.stdout.splitlines() if l.startswith('RESULT ')), None)
            self.assertIsNotNone(line, run.stdout[-3000:])
            return json.loads(line[7:])

    def check(self, case):
        r = self.run_case(case)
        self.assertTrue(r['startup_done'], r)
        for i, one in enumerate(r['rounds']):
            self.assertTrue(one['done'], (case, i, one))

    def test_analysis_finishes_after_each_close(self):
        self.check('stay')

    def test_analysis_finishes_after_each_close_that_goes_back_to_another_app(self):
        self.check('back')

    def test_a_conversion_left_in_the_memo_does_not_hold_the_analysis(self):
        # 2026-10-19: a conversion left unconfirmed in the memo stays in its IME context
        # while CorrectNote has no focus; waiting for it to end held the work until a click.
        r = self.run_case('stale_ime')
        if not r.get('composition_set'):
            self.skipTest('this IME does not take a composition set by the program')
        self.assertTrue(r['startup_done'], r)
        self.assertTrue(r['rounds'][0]['done'], r)
        self.assertTrue(r['marks_cleared'], r)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1])
    else:
        unittest.main()
