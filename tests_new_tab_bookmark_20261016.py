# -*- coding: utf-8 -*-
"""New tabs no longer get a bookmark on line 1 (2026-10-16 うにさん).

「新規タブ作成時に、1行目をブックマークしておくのをやめる。」

Bookmarks already saved in existing tabs (including an automatic line-1 one)
stay as they are. Moving to the next/previous bookmark in a tab without any
does not fail and does not move the cursor.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from session import SessionStore, fresh_tab, new_tab


class SessionBookmarkTests(unittest.TestCase):
    def test_every_way_of_making_a_new_tab_has_no_bookmark(self):
        self.assertEqual(fresh_tab()['bookmarks'], [])
        s = SessionStore()
        s.reset_fresh()                     # first start / unreadable session
        self.assertEqual(s.tabs[0]['bookmarks'], [])
        s.add_tab()                         # new tab (button, Ctrl+T)
        self.assertEqual(s.tabs[1]['bookmarks'], [])
        s.remove_tab(1)
        s.remove_tab(0)                     # closing the last tab makes a new one
        self.assertEqual(s.tabs[0]['bookmarks'], [])

    def test_saved_bookmarks_stay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'session.json')
            s = SessionStore(path)
            s.tabs = [new_tab('一\n二\n三', bookmarks=[1]), new_tab('あ\nい', bookmarks=[1, 2])]
            s.active = 0
            s.save()
            again = SessionStore(path)
            self.assertTrue(again.load())
            self.assertEqual([t['bookmarks'] for t in again.tabs], [[1], [1, 2]])
            again.add_tab()
            self.assertEqual([t['bookmarks'] for t in again.tabs], [[1], [1, 2], []])
        self.assertEqual(fresh_tab(bookmarks=[3, 7])['bookmarks'], [3, 7])


def child():
    import tkinter as tk
    sys.path.insert(0, os.getcwd())
    import app
    from session import new_tab as make
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                     encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        make(text='一行目\n二行目\n三行目', bookmarks=[1, 3])])), encoding='utf8')
    root = tk.Tk()
    root.withdraw()
    a = None
    out = {}
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
            a = app.CorrectNoteApp(root)
            root.update()
            out['existing'] = sorted(a.bookmarks)
            a.new_file()
            root.update()
            out['new_tab'] = sorted(a.bookmarks)
            out['new_tab_saved'] = a.session.current()['bookmarks']
            a.editor.insert('1.0', 'あ\nい\nう')
            a._on_change()
            a.editor.mark_set('insert', '2.1')
            errors = []
            statuses = []
            for forward in (True, False):
                try:
                    a._goto_bookmark(forward=forward)
                except Exception as e:      # noqa: BLE001
                    errors.append(repr(e))
                # Read it at once: the analysis may write its own status later.
                statuses.append(a.status.cget('text'))
                root.update()
            out['errors'] = errors
            out['cursor'] = a.editor.index('insert')
            out['status'] = statuses
            a._switch_tab(0)
            root.update()
            out['existing_after'] = sorted(a.bookmarks)
            out['existing_saved'] = a.session.tabs[0]['bookmarks']
            print('RESULT ' + json.dumps(out, ensure_ascii=False), flush=True)
    finally:
        if a:
            a._on_close()
        else:
            root.destroy()


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class AppBookmarkTests(unittest.TestCase):
    def test_new_tab_existing_tab_and_moving_without_bookmarks(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-bookmark-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):
                    shutil.copyfile(path, dest / path.name)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8',
                                 timeout=150)
            line = next((l for l in run.stdout.splitlines() if l.startswith('RESULT ')), None)
            self.assertIsNotNone(line, run.stdout[-3000:])
            r = json.loads(line[7:])
        self.assertEqual(r['existing'], [1, 3])
        self.assertEqual(r['new_tab'], [])
        self.assertEqual(r['new_tab_saved'], [])
        self.assertEqual(r['errors'], [])
        self.assertEqual(r['cursor'], '2.1')            # no jump anywhere
        self.assertEqual(r['status'], ['ブックマークがありません'] * 2)
        self.assertEqual(r['existing_after'], [1, 3])
        self.assertEqual(r['existing_saved'], [1, 3])


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
