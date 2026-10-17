# -*- coding: utf-8 -*-
"""Options to leave the clipboard alone (2026-10-16 うにさん).

「簡易入力を閉じたときに、クリップボードに入れるかどうかをオプションでオンオフする
  単語帳をクリックして、クリップボードに入れるかどうかをオプションでオンオフする
  デフォルトはどちらもオンで、入れる」

With an option off the text still reaches the field: CorrectNote's own fields
directly, another app with Ctrl+V on a lent clipboard whose old contents come
back afterwards. The real clipboard is never touched here (a stand-in).
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
from types import SimpleNamespace
from unittest.mock import Mock, patch

import clipboard_keep


class FakeClipboard:
    """Stands in for the Windows clipboard: {format: data} and a sequence number."""

    def __init__(self, items=None, handles=()):
        self.items = dict(items or {})
        self.handles = set(handles)
        self.seq = 1
        self.opened = 0
        self.fail_open = False
        self.fail_put = False
        self.discarded = []

    def open(self):
        if self.fail_open:
            return False
        self.opened += 1
        return True

    def close(self):
        self.opened -= 1

    def empty(self):
        self.items.clear()
        self.seq += 1

    def sequence(self):
        return self.seq

    NAMES = {'ExcludeClipboardContentFromMonitorProcessing': 0xC101,
             'CanIncludeInClipboardHistory': 0xC102, 'CanUploadToCloudClipboard': 0xC103}

    def register(self, name):
        return self.NAMES[name]

    def plain(self):
        """The contents without the history/cloud marks."""
        return {k: v for k, v in self.items.items() if k not in self.NAMES.values()}

    def formats(self):
        return list(self.items) + sorted(self.handles)

    def take(self, fmt):
        return self.items.get(fmt)

    def put(self, fmt, data):
        if self.fail_put and isinstance(data, str):
            return False
        self.items[fmt] = data
        self.seq += 1
        return True

    def discard(self, data):
        self.discarded.append(data)


HTML = 49350
OLD = {13: '前の文'.encode('utf-16-le') + bytes(2), 8: b'BMPDATA', HTML: b'<b>x</b>'}
MARKS = {0xC101: b'', 0xC102: bytes(4), 0xC103: bytes(4)}


class SettingsTests(unittest.TestCase):
    def test_both_default_on(self):
        from settings import Settings
        s = Settings()
        self.assertIs(s.get('quick_close_clipboard'), True)
        self.assertIs(s.get('word_book_clipboard'), True)

    def test_old_settings_file_reads_on(self):
        from settings import Settings
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'settings.json')
            Path(path).write_text(json.dumps({'quick_paste_back': False, 'theme': 'light'}), encoding='utf-8')
            s = Settings(path)
            self.assertIs(s.get('quick_paste_back'), False)
            self.assertIs(s.get('quick_close_clipboard'), True)
            self.assertIs(s.get('word_book_clipboard'), True)

    def test_off_is_saved_and_read_back(self):
        from settings import Settings
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'settings.json')
            s = Settings(path)
            s.set('quick_close_clipboard', False)
            s.set('word_book_clipboard', False)
            s.save()
            again = Settings(path)
            self.assertIs(again.get('quick_close_clipboard'), False)
            self.assertIs(again.get('word_book_clipboard'), False)


class LendTests(unittest.TestCase):
    def test_lend_puts_text_and_restore_gives_everything_back(self):
        board = FakeClipboard(OLD, handles={9})
        lent = clipboard_keep.lend('単語', board)
        self.assertEqual(board.plain(), {13: '単語'})
        self.assertEqual(lent.skipped, [9])
        self.assertTrue(lent.restore())
        self.assertEqual(board.plain(), OLD)
        self.assertEqual(board.opened, 0)
        self.assertFalse(lent.restore())         # only once

    def test_empty_clipboard_comes_back_empty(self):
        board = FakeClipboard()
        lent = clipboard_keep.lend('単語', board)
        self.assertTrue(lent.restore())
        self.assertEqual(board.plain(), {})

    def test_a_newer_copy_by_the_user_is_kept(self):
        board = FakeClipboard(OLD)
        emf = ('emf', 77)
        board.items[14] = emf
        lent = clipboard_keep.lend('単語', board)
        board.empty()
        board.put(13, '新しくコピーした文')
        self.assertFalse(lent.restore())
        self.assertEqual(board.items, {13: '新しくコピーした文'})
        self.assertIn(emf, board.discarded)

    def test_clipboard_busy_changes_nothing(self):
        board = FakeClipboard(OLD)
        board.fail_open = True
        self.assertIsNone(clipboard_keep.lend('単語', board))
        self.assertEqual(board.plain(), OLD)

    def test_text_not_accepted_puts_old_contents_back(self):
        board = FakeClipboard(OLD)
        board.fail_put = True
        self.assertIsNone(clipboard_keep.lend('単語', board))
        self.assertEqual(board.plain(), OLD)
        self.assertEqual(board.opened, 0)

    def test_lent_text_and_restored_contents_stay_out_of_history_and_cloud(self):
        """Win+V history and the cloud clipboard: three registered marks each time."""
        board = FakeClipboard(OLD)
        lent = clipboard_keep.lend('単語', board)
        self.assertEqual({k: board.items[k] for k in MARKS}, MARKS)
        self.assertTrue(lent.restore())
        self.assertEqual({k: board.items[k] for k in MARKS}, MARKS)
        self.assertEqual(board.plain(), OLD)

    def test_handle_formats_are_not_copied(self):
        for fmt in (2, 3, 9, 0x80, 0x82, 0x83, 0x8E, 0x200, 0x2FF, 0x300, 0x3FF):
            self.assertFalse(clipboard_keep._keepable(fmt), fmt)
        for fmt in (1, 7, 8, 13, 14, 15, 16, 17, 0xC000, HTML):
            self.assertTrue(clipboard_keep._keepable(fmt), fmt)


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class WordBookOptionTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        import app
        from word_book import WordBook
        global word_book
        import word_book
        self.root = tk.Tk()
        self.root.withdraw()
        self.calls = []
        self.root.clipboard_clear = lambda *a, **k: self.calls.append('clear')
        self.root.clipboard_append = lambda text, **k: self.calls.append(('append', text))
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.status = tk.Label(self.root)
        from settings import Settings
        a.settings = Settings()
        self.a = a
        self.book = WordBook.__new__(WordBook)
        self.book.app = a
        self.book.window = None
        self.book._focus_job = self.book._insert_job = None
        self.board = FakeClipboard(OLD)

    def tearDown(self):
        self.root.destroy()

    def native(self, owner):
        user = SimpleNamespace(GetForegroundWindow=lambda: 0x1234)
        n = SimpleNamespace(user=user, previous=(0x1234, owner), paste=Mock(return_value=True),
                            restore_previous=lambda: True, hwnd=0x9999)
        self.book._native = n
        return n

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def test_on_copies_as_before(self):
        self.book.copy('単語')
        self.assertEqual(self.calls, ['clear', ('append', '単語')])

    def test_off_leaves_clipboard_and_still_pastes_into_another_app(self):
        self.a.settings.set('word_book_clipboard', False)
        n = self.native(os.getpid() + 1)
        seen = []
        n.paste.side_effect = lambda hwnd: seen.append(self.board.plain()) or True
        with patch.object(clipboard_keep, '_backend', return_value=self.board):
            self.book.copy('単語')                       # goes on to insert by itself
            self.assertEqual(self.calls, [])
            self.pump((word_book.INSERT_DELAY_MS + clipboard_keep.RESTORE_DELAY_MS) / 1000 + 0.4)
            n.paste.assert_called_once_with(0x1234)
            self.assertEqual(seen, [{13: '単語'}])        # the paste read the word
        self.assertEqual(self.board.plain(), OLD)          # then the old contents came back
        self.assertEqual(self.calls, [])
        self.assertEqual(self.a.status.cget('text'), '単語帳の文字を入れました')

    def test_off_and_paste_not_possible_restores_at_once(self):
        self.a.settings.set('word_book_clipboard', False)
        n = self.native(os.getpid() + 1)
        n.paste.return_value = False
        with patch.object(clipboard_keep, '_backend', return_value=self.board):
            self.assertFalse(self.book._insert_into((0x1234, os.getpid() + 1), '単語'))
        self.assertEqual(self.board.plain(), OLD)

    def test_off_into_own_field_needs_no_clipboard(self):
        self.a.settings.set('word_book_clipboard', False)
        self.native(os.getpid())
        got = []
        self.book._insert_into_app = lambda hwnd, text: got.append(text) or True
        with patch.object(clipboard_keep, '_backend', side_effect=AssertionError('clipboard used')):
            self.assertTrue(self.book._insert_into((0x1234, os.getpid()), '単語'))
        self.assertEqual(got, ['単語'])
        self.assertEqual(self.calls, [])


def child(case):
    """A real app in a copied folder: open quick input, type, close."""
    import tkinter as tk
    import app
    import quick_return
    from session import new_tab
    import tests_clipboard_options_20261016 as T
    settings = dict(layout='split', input_method='kana', input_method_auto=False)
    settings.update(json.loads(case))
    Path('settings.json').write_text(json.dumps(settings), encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='')])), encoding='utf8')
    root = tk.Tk()
    root.withdraw()
    calls = []
    root.clipboard_clear = lambda *a, **k: calls.append('clear')
    root.clipboard_append = lambda text, **k: calls.append(('append', text))
    board = T.FakeClipboard(T.OLD)
    restored = []

    def give_back(target, root_, paste=False):
        restored.append((paste, board.plain()))
        return True
    a = None
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None), \
                patch.object(tk.Toplevel, 'winfo_pointerxy', return_value=(300, 200)), \
                patch.object(quick_return, 'restore', give_back), \
                patch.object(clipboard_keep, '_backend', return_value=board):
            a = app.CorrectNoteApp(root)
            root.update()
            a._open_quick_capture()
            a._quick_text.insert('1.0', '閉じる文')
            a._quick_return = quick_return.Target(1, 2, 3, 4, True)
            a._close_quick_capture()
            status = a.status.cget('text')
            end = time.monotonic() + (quick_return.PASTE_DELAY_MS + clipboard_keep.RESTORE_DELAY_MS) / 1000 + 0.5
            while time.monotonic() < end:
                root.update()
                time.sleep(0.01)
            out = dict(calls=calls, restored=restored, board=board.plain() == T.OLD,
                       memo=a.editor.get('1.0', 'end-1c'), status=status)
            print('RESULT ' + json.dumps(out, ensure_ascii=False, default=str), flush=True)
    finally:
        if a:
            a._on_close()
        else:
            root.destroy()


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class QuickCloseOptionTests(unittest.TestCase):
    def run_case(self, **case):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-clip-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):
                    shutil.copyfile(path, dest / path.name)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name),
                                  '--child', json.dumps(case)], cwd=dest, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, encoding='utf8', timeout=150)
            line = next((l for l in run.stdout.splitlines() if l.startswith('RESULT ')), None)
            self.assertIsNotNone(line, run.stdout[-3000:])
            return json.loads(line[7:])

    def test_default_puts_text_on_clipboard_and_pastes(self):
        r = self.run_case()
        self.assertEqual(r['calls'], ['clear', ['append', '閉じる文']])
        self.assertEqual([p for p, b in r['restored']], [True])
        self.assertTrue(r['board'])                  # the lending path was not used
        self.assertIn('閉じる文', r['memo'])
        self.assertIn('クリップボードとメモ', r['status'])

    def test_off_pastes_with_a_lent_clipboard_and_gives_it_back(self):
        r = self.run_case(quick_close_clipboard=False)
        self.assertEqual(r['calls'], [])
        self.assertEqual(r['restored'], [[True, {'13': '閉じる文'}]])
        self.assertTrue(r['board'])                  # old contents back after the paste
        self.assertIn('閉じる文', r['memo'])
        self.assertNotIn('クリップボード', r['status'])

    def test_both_off_keeps_the_text_in_the_memo_only(self):
        r = self.run_case(quick_close_clipboard=False, quick_paste_back=False)
        self.assertEqual(r['calls'], [])
        self.assertEqual([p for p, b in r['restored']], [False])
        self.assertTrue(r['board'])
        self.assertIn('閉じる文', r['memo'])


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1])
    else:
        unittest.main()
