# -*- coding: utf-8 -*-
"""Right button + wheel switches the tab; pressing the right button again right after must start a right-drag
scroll, not the right double press (overview). 2026-11-07 うにさん「右クリックホイールでタブ移動した直後に、
右クリックを押し直し続けてスクロールしようと思っても、スクロールできない」. An isolated copy of the app with
made-up text; the events are generated in its own window only."""
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
    assert (here / '.ui-right-test-isolated').is_file()
    assert Path(app.__file__).resolve().parent == here
    text = '\n'.join('%d 行目の作り物の文です。' % k for k in range(1, 300))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
        unified_autofix=False, right_drag_inertia=False, wheel_inertia=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text), new_tab(text=text)]),
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
            root.geometry('900x520+40+40')
            pump(3.0)
            ed = a.editor
            x, y = ed.winfo_width() // 2, ed.winfo_height() // 2
            rx, ry = ed.winfo_rootx() + x, ed.winfo_rooty() + y
            t0 = int(ed.tk.call('clock', 'milliseconds')) & 0x7fffffff
            start_tab = a.session.active
            common = dict(x=x, y=y, rootx=rx, rooty=ry)
            ed.event_generate('<ButtonPress-3>', time=t0, **common); pump(.05)
            ed.event_generate('<MouseWheel>', delta=-120, state=0x400, time=t0 + 80, **common); pump(.6)
            assert a.session.active != start_tab, 'the right-held wheel did not switch the tab'
            ed.event_generate('<ButtonRelease-3>', state=0x400, time=t0 + 200, **common); pump(.05)
            ed.yview_moveto(0); pump(.3)
            before = ed.yview()[0]
            ed.event_generate('<ButtonPress-3>', time=t0 + 320, **common); pump(.05)
            assert getattr(a, '_overview', None) is None, 'the press after the tab switch was taken as a right double press'
            # The drag counts the movement from the real pointer (app._drag_motion: it keeps scrolling at a screen
            # edge), so generated motions cannot move the view: what is checked is that a right-drag scroll started
            for k in range(1, 4):
                ed.event_generate('<B3-Motion>', state=0x400, x=x, y=y - 12 * k, rootx=rx, rooty=ry - 12 * k,
                                  time=t0 + 340 + 16 * k)
                pump(.02)
            drag = getattr(a, '_drag', None)
            assert drag is not None and drag['widget'] is ed and drag['mode'] == 'scroll', ('no right-drag scroll', drag)
            assert getattr(a, '_overview', None) is None
            ed.event_generate('<ButtonRelease-3>', state=0x400, time=t0 + 600, x=x, y=y - 36, rootx=rx, rooty=ry - 36)
            pump(.3)
            assert not errors, errors
            print('RIGHT_AFTER_TAB_WHEEL_PASSED', flush=True)
        finally:
            if a is not None: a._on_close()
            else: root.destroy()


class RightAfterTabWheelTests(unittest.TestCase):
    def test_right_drag_right_after_a_tab_switch(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-right-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-right-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=240)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('RIGHT_AFTER_TAB_WHEEL_PASSED', run.stdout, run.stdout)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
