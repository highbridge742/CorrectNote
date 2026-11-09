# -*- coding: utf-8 -*-
"""The all-tab search results window fits its height to the results each time (2026-11-08 うにさん「全タブ検索は、
結果の一覧の下に余白が出ないように縦幅を短くする。結果のたびに変える」), never over the first height, keeping its
width; the buttons at the bottom stay visible however short the window is. An isolated copy, made-up text."""
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
    assert (here / '.ui-find-fit-test-isolated').is_file()
    many = '\n'.join('資料の行%d。' % i for i in range(60))
    tabs = [new_tab(text='一件だけの語。\n資料は三つ。資料。資料。'), new_tab(text=many)]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=tabs), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    tk.Misc.clipboard_get = lambda self, **kw: ''
    tk.Misc.clipboard_clear = lambda self, **kw: None
    tk.Misc.clipboard_append = lambda self, s, **kw: None

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if until is not None and until(): return True
        return False
    out = {}

    def search(word):
        a._find_query.set(word)
        a._do_find_all_tabs()
        pump(3.0, lambda: '件' in a._all_tab_notice.cget('text') and '中' not in a._all_tab_notice.cget('text'))
        pump(0.3)
        d = a._all_tab_dialog
        b = a._all_tab_dialog.winfo_children()
        buttons = [w for w in d.winfo_children() if isinstance(w, tk.Frame) and any(isinstance(c, tk.Button) for c in w.winfo_children())][0]
        tree = a._all_tab_tree
        bottom_of_list = tree.winfo_rooty() + tree.winfo_height()
        return dict(h=d.winfo_height(), w=d.winfo_width(), hits=len(a._all_tab_hits),
                    buttons_visible=buttons.winfo_ismapped() and buttons.winfo_y() + buttons.winfo_height() <= d.winfo_height(),
                    rows_shown=int(str(tree.cget('height'))),
                    gap=d.winfo_rooty() + d.winfo_height() - bottom_of_list)
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.deiconify(); pump(1.5)                       # the results window is transient: it shows with the main window
        a.open_find_dialog(False)
        a._ensure_all_tab_results()
        a._all_tab_dialog.deiconify(); pump(0.3)
        out['first_h'] = a._all_tab_dialog.winfo_height()
        out['one'] = search('一件')
        out['few'] = search('三つ')
        out['some'] = search('資料。')
        out['many'] = search('資料')
        out['none'] = search('見つからない語')
        # the width set by hand stays; the height fits again
        a._all_tab_dialog.geometry('900x400'); pump(0.3)
        out['hand'] = search('資料。')
        # squeezed by hand: the buttons are still there
        a._all_tab_dialog.geometry('900x160'); pump(0.3)
        d = a._all_tab_dialog
        buttons = [w for w in d.winfo_children() if isinstance(w, tk.Frame) and any(isinstance(c, tk.Button) for c in w.winfo_children())][0]
        out['squeezed_buttons'] = buttons.winfo_ismapped() and buttons.winfo_y() + buttons.winfo_height() <= d.winfo_height()
        assert not errors, errors
        print('FIT', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


class FindAllFit(unittest.TestCase):
    def test_height_fits_the_results(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-find-fit-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-find-fit-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('FIT ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('FIT '):])
            print(got)
            first = got['first_h']
            self.assertEqual(got['one']['hits'], 1, got)
            self.assertEqual(got['few']['hits'], 1, got)
            self.assertEqual(got['some']['hits'], 2, got)
            self.assertGreater(got['many']['hits'], 30, got)
            for name in ('one', 'few', 'some', 'many', 'none', 'hand'):
                self.assertTrue(got[name]['buttons_visible'], (name, got))
                self.assertLessEqual(got[name]['h'], first, (name, got))
            self.assertLess(got['one']['h'], first, got)
            self.assertLess(got['one']['h'], got['some']['h'], got)
            self.assertEqual(got['some']['rows_shown'], 2, got)
            self.assertGreater(got['many']['h'], first - 2 * (got['some']['h'] - got['one']['h']), got)   # whole rows up to the first height
            self.assertEqual(len({got[n]['gap'] for n in ('one', 'some', 'many', 'none', 'hand')}), 1, got)   # no blank under the list
            self.assertEqual(got['none']['h'], got['one']['h'], got)
            self.assertEqual(got['hand']['w'], 900, got)
            self.assertEqual(got['hand']['h'], got['some']['h'], got)
            self.assertTrue(got['squeezed_buttons'], got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
