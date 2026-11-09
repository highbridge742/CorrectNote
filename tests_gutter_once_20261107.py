# -*- coding: utf-8 -*-
"""The line-number gutters are drawn once per key, from the state after the key (2026-11-07, Enter held down).
After each Enter, once the app is idle, both gutters hold exactly what a fresh, immediate redraw draws
(the numbers, their places, the cursor row's band). An isolated copy of the app, made-up text."""
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
    from tests_tk_keys import deliver_key
    here = Path.cwd().resolve()
    assert (here / '.ui-gutter-test-isolated').is_file()
    text = '\n'.join('%d 行目の作り物の文です。' % k for k in range(1, 160))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                        encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    clip = []
    root.clipboard_clear = lambda **kw: clip.clear(); root.clipboard_append = lambda t, **kw: clip.append(t)
    root.clipboard_get = lambda **kw: ''.join(clip)
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
        assert not errors, errors

    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None):
        try:
            a = app.CorrectNoteApp(root)
            root.geometry('900x520+40+40')
            pump(2.0)
            ed = a.editor
            ed.mark_set('insert', '30.end'); ed.see('insert'); ed.focus_force(); pump(0.3)
            counts = []
            for k in range(25):
                real = app.LineNumberGutter.redraw
                calls = []
                app.LineNumberGutter.redraw = lambda self, real=real: (calls.append(self), real(self))[1]
                deliver_key(ed, '<Return>', 'Return', 13, char=chr(13))
                deliver_key(ed, '<KeyPress>', 'Return', 13, char=chr(13))
                root.update()
                app.LineNumberGutter.redraw = real
                counts.append(len(calls))
                for gutter in (a.editor_gutter, a.result_gutter):
                    drawn = list(gutter._numbers_drawn or ())
                    gutter._numbers_drawn = None          # draw again from nothing, now
                    gutter.redraw()
                    assert gutter._numbers_drawn == drawn, (k, str(gutter))
                    shown = [(gutter.itemcget(i, 'text'), tuple(gutter.coords(i))) for i in gutter.find_withtag('num')]
                    assert shown == [(o['text'], w) for kind, w, o in drawn if kind == 'text'], k
            assert not errors, errors
            print('GUTTER_ONCE', json.dumps(counts), flush=True)
            print('GUTTER_ONCE_PASSED', flush=True)
        finally:
            a._on_close()


class GutterOnceTests(unittest.TestCase):
    def test_the_gutters_after_each_enter_are_a_fresh_drawing(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-gutter-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-gutter-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=240)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('GUTTER_ONCE_PASSED', run.stdout, run.stdout)
            counts = json.loads(next(l for l in run.stdout.splitlines() if l.startswith('GUTTER_ONCE '))[12:])
            # one drawing per gutter per key (two gutters); before, the cursor row drew them again at once
            self.assertLessEqual(max(counts), 2, counts)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
