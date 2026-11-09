# -*- coding: utf-8 -*-
"""The search window (2026-11-08 うにさん「検索ウィンドウは右の余白が大きいので、全タブ検索ボタンを1行下へ。元の行に
戻るは2行下へ。4つのチェックボックスは、畳めるようにする」): 全タブ検索 is on the row under 次を検索, 元の行に戻る on
the row under that, the window is narrower than before; the four options fold and unfold, keep their values and still
work while folded, and the folded state lasts while the app runs. An isolated copy, made-up text; CN_FIND_LAYOUT2=0
is the old form."""
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
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-find-layout-test-isolated').is_file()
    tabs = [new_tab(text='Apple apple APPLE.\n資料の行。')]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=tabs), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    tk.Misc.clipboard_get = lambda self, **kw: ''
    tk.Misc.clipboard_clear = lambda self, **kw: None
    tk.Misc.clipboard_append = lambda self, s, **kw: None

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)

    def button(text):
        stack = [a._find_dialog]
        while stack:
            w = stack.pop()
            if isinstance(w, tk.Button) and w.cget('text').startswith(text):
                return w
            stack.extend(w.winfo_children())
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        pump(1.0)
        a.open_find_dialog(False); pump(0.4)
        d = a._find_dialog
        out['width'] = d.winfo_width()
        out['y'] = {k: button(k).winfo_rooty() for k in ('次を検索', '前を検索', '全タブ検索', '元の行に戻る')}
        out['x'] = {k: button(k).winfo_rootx() for k in ('次を検索', '全タブ検索', '元の行に戻る')}
        a._find_match_case.set(True)
        a._find_query.set('apple')
        a._do_find(False); pump(0.2)
        out['open_hits'] = len(a.editor.tag_ranges('found')) // 2
        if os.environ.get('CN_FIND_LAYOUT2') != '0':
            out['head_open'] = a._find_opts_head.cget('text')
            h_open = d.winfo_height()
            a._toggle_find_options(); pump(0.3)
            out['head_folded'] = a._find_opts_head.cget('text')
            out['folded_shorter'] = d.winfo_height() < h_open
            out['opts_hidden'] = not a._find_opts_frame.winfo_ismapped()
            out['value_kept'] = a._find_match_case.get()
            a._do_find(False); pump(0.2)
            out['folded_hits'] = len(a.editor.tag_ranges('found')) // 2
            a._find_regex.set(False); a._find_wrap.set(True); pump(0.1)
            out['head_after_change'] = a._find_opts_head.cget('text')
            # closed and opened again: still folded
            a._close_find_dialog(); pump(0.2)
            a.open_find_dialog(False); pump(0.4)
            out['reopen_folded'] = not a._find_opts_frame.winfo_ismapped()
            a._toggle_find_options(); pump(0.3)
            out['unfolded'] = a._find_opts_frame.winfo_ismapped()
            out['head_unfolded'] = a._find_opts_head.cget('text')
            # replace: the replace buttons go on the first row
            a._close_find_dialog(); pump(0.2)
            a.open_find_dialog(True); pump(0.4)
            out['replace_y'] = [button(k).winfo_rooty() for k in ('次を検索', '置換', 'すべて置換')]
            out['replace_find_all_y'] = button('全タブ検索').winfo_rooty()
        a._find_match_case.set(False)
        assert not errors, errors
        print('LAYOUT', json.dumps(out, ensure_ascii=False), flush=True)
        a._close_find_dialog()
        a._on_close()


class FindLayout2(unittest.TestCase):
    def run_child(self, env):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-find-layout-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-find-layout-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300, env=dict(os.environ, **env))
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('LAYOUT ')]
            self.assertTrue(line, run.stdout[-3000:])
            return json.loads(line[0][len('LAYOUT '):])

    def test_layout_and_folding(self):
        old = self.run_child({'CN_FIND_LAYOUT2': '0'})
        new = self.run_child({})
        print('old', old); print('new', new)
        y = new['y']
        self.assertLessEqual(abs(y['次を検索'] - y['前を検索']), 2, new)        # the primary button has no border: 1px
        self.assertGreater(y['全タブ検索'], y['次を検索'], new)
        self.assertGreater(y['元の行に戻る'], y['全タブ検索'], new)
        self.assertEqual(new['x']['全タブ検索'], new['x']['次を検索'], new)
        self.assertEqual(new['x']['元の行に戻る'], new['x']['次を検索'], new)
        self.assertLessEqual(max(old['y'].values()) - min(old['y'].values()), 2, old)   # the old form: one row
        self.assertLess(new['width'], old['width'], (new, old))
        self.assertEqual(new['open_hits'], 1, new)                      # case kept: only "apple"
        self.assertEqual(old['open_hits'], 1, old)
        self.assertTrue(new['head_open'].startswith('▾'), new)
        self.assertTrue(new['head_folded'].startswith('▸'), new)
        self.assertIn('大文字と小文字を区別する', new['head_folded'], new)
        self.assertTrue(new['folded_shorter'], new)
        self.assertTrue(new['opts_hidden'], new)
        self.assertTrue(new['value_kept'], new)
        self.assertEqual(new['folded_hits'], 1, new)
        self.assertIn('折り返して検索', new['head_after_change'], new)
        self.assertTrue(new['reopen_folded'], new)
        self.assertTrue(new['unfolded'], new)
        self.assertTrue(new['head_unfolded'].startswith('▾'), new)
        self.assertLessEqual(max(new['replace_y']) - min(new['replace_y']), 2, new)
        self.assertGreater(new['replace_find_all_y'], new['replace_y'][0], new)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
