# -*- coding: utf-8 -*-
"""The mouse wheel scrolls the panes while the picture is shown through them (2026-11-07 うにさん「ホイールでの
スクロールが効かない。2日前から」). Tk gives <MouseWheel> to the window under the pointer, which is the picture's
Canvas behind a see-through pane: it must reach the pane's own binding. An isolated copy of the app, made-up text;
it shows a small window and posts the wheel messages to that window only (the real mouse does not move)."""
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
    import ctypes
    import ctypes.wintypes as wt
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    import paper_window
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-wheel-test-isolated').is_file()
    assert Path(app.__file__).resolve().parent == here
    if not paper_window.available():
        print('WHEEL_THROUGH_SKIPPED', flush=True)
        return
    user32 = ctypes.WinDLL('user32')
    user32.PostMessageW.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    text = '\n'.join('%d 行目の作り物の文です。' % k for k in range(1, 300))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
        decor='nami', unified_autofix=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); a = None; errors = []
    clipboard = []
    root.clipboard_clear = lambda **kw: clipboard.clear()
    root.clipboard_append = lambda t, **kw: clipboard.append(t)
    root.clipboard_get = lambda **kw: ''.join(clipboard)
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            time.sleep(.005)
        assert not errors, errors

    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
        try:
            a = app.CorrectNoteApp(root)
            root.geometry('900x520+40+40'); root.attributes('-topmost', True)
            root.lift(); root.focus_force(); a.editor.focus_force()
            pump(3.0)
            for pane in (a.editor, a.result_view):
                paper = getattr(pane, '_correctnote_paper', None)
                assert paper is not None and paper._through, ('the picture is not shown through', pane)
            import appearance
            went = []
            real_forward = appearance.forward_wheel
            def forward(event, pane):
                went.append((str(event.widget), str(pane), event.delta))
                return real_forward(event, pane)
            appearance.forward_wheel = forward
            got = []
            root.bind_class('wheelrec', '<MouseWheel>', lambda e: got.append((str(e.widget), e.delta)))
            for w in (a.editor, a.result_view):
                w.bindtags(('wheelrec',) + tuple(w.bindtags()))
                back = getattr(getattr(w, '_correctnote_paper', None), '_back', None)
                if back is not None:
                    back.bindtags(('wheelrec',) + tuple(back.bindtags()))
            for pane in (a.editor, a.result_view):
                a.editor.yview_moveto(0); a.result_view.yview_moveto(0); pump(.3)
                del went[:]; del got[:]
                under = str(root.winfo_containing(pane.winfo_rootx() + pane.winfo_width() // 2, pane.winfo_rooty() + pane.winfo_height() // 2))
                before = a.editor.yview()[0]
                x, y = pane.winfo_rootx() + pane.winfo_width() // 2, pane.winfo_rooty() + pane.winfo_height() // 2
                if under == 'None':
                    print('WHEEL_THROUGH_COVERED', str(pane), flush=True)     # another window lies over the test window
                    continue
                for _ in range(3):
                    user32.PostMessageW(int(pane.winfo_id()), 0x020A, ((-120) & 0xFFFF) << 16, (x & 0xFFFF) | ((y & 0xFFFF) << 16))
                    pump(.15)
                after = a.editor.yview()[0]
                assert after > before, ('the wheel did not scroll', str(pane), before, after, 'under', under, 'went', went, 'got', got)
                # the other pane follows (the same row at the top)
                assert abs(float(a.result_view.index('@0,0').split('.')[0]) - float(a.editor.index('@0,0').split('.')[0])) <= 1
            assert not errors, errors
            print('WHEEL_THROUGH_PASSED', flush=True)
        finally:
            if a is not None: a._on_close()
            else: root.destroy()


class WheelThroughTests(unittest.TestCase):
    def test_the_wheel_scrolls_a_see_through_pane(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-wheel-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-wheel-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=240)
            self.assertEqual(run.returncode, 0, run.stdout)
            if 'WHEEL_THROUGH_SKIPPED' in run.stdout:
                self.skipTest('no child layered windows here')
            self.assertIn('WHEEL_THROUGH_PASSED', run.stdout, run.stdout)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
