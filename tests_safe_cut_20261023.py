# -*- coding: utf-8 -*-
"""A cut deletes only what is on the clipboard (2026-10-23 うにさん「300行ぐらいを解析中にカットすると、
クリップボードに入らず、消えました」).

Tk's own cut deletes the selection even when the clipboard could not be opened (another program
holding it for a moment). safe_cut puts the text there, reads it back, tries again a few times, and
deletes only once it is there; otherwise the text stays and the status line says so. The real
clipboard is not used: a stand-in backend plays the clipboard that is busy for a while. The real
clipboard and a second process holding it: tools_local/emphasis_20261023/probe_cut.py."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, safe_cut


class BusyClipboard:
    """Cannot be opened `busy` times, then holds whatever was last put there."""

    def __init__(self, busy=0):
        self.busy = busy; self.text = None; self.staged = None

    def open(self):
        if self.busy > 0:
            self.busy -= 1
            self.staged = None          # the clipboard could not take it this time
            return False
        if self.staged is not None:
            self.text, self.staged = self.staged, None
        return True

    def close(self):
        pass

    def take(self, fmt):
        return None if self.text is None else (self.text + '\0').encode('utf-16-le')


class SafeCutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root; a.status = tk.Label(self.root)
        a.editor = tk.Text(self.root, undo=True)
        a.editor.insert('1.0', '\n'.join('%d行目' % i for i in range(1, 11)))
        a.editor.edit_separator()
        a.editor.tag_add('sel', '2.0', '6.0')

    def tearDown(self):
        self.root.destroy()

    def cut(self, board):
        a = self.a
        put = lambda text: setattr(board, 'staged', text)
        with patch.object(safe_cut, 'WAIT_S', 0), \
             patch.object(a.editor, 'clipboard_clear', lambda **kw: None), \
             patch.object(a.editor, 'clipboard_append', lambda text, **kw: put(text)), \
             patch('clipboard_keep._backend', return_value=board), \
             patch.object(safe_cut, 'sys', SimpleNamespace(platform='win32')):
            return a._on_cut_event(str(a.editor))

    def rows(self):
        return int(self.a.editor.index('end-1c').split('.')[0])

    def test_deletes_once_the_clipboard_holds_it(self):
        board = BusyClipboard()
        self.assertEqual(self.cut(board), 'break')
        self.assertEqual(self.rows(), 6)
        self.assertEqual(board.text, '2行目\n3行目\n4行目\n5行目\n')
        self.a.editor.edit_undo()
        self.assertEqual(self.rows(), 10)

    def test_a_busy_moment_is_waited_out(self):
        board = BusyClipboard(busy=2)
        self.cut(board)
        self.assertEqual(self.rows(), 6)
        self.assertEqual(board.text, '2行目\n3行目\n4行目\n5行目\n')

    def test_nothing_is_deleted_when_the_clipboard_never_takes_it(self):
        board = BusyClipboard(busy=99)
        self.assertEqual(self.cut(board), 'break')
        self.assertEqual(self.rows(), 10)                        # every row kept
        self.assertIsNone(board.text)
        self.assertIn('切り取りませんでした', self.a.status.cget('text'))

    def test_without_a_selection_tk_goes_on(self):
        self.a.editor.tag_remove('sel', '1.0', 'end')
        self.assertEqual(self.cut(BusyClipboard()), '')
        self.assertEqual(self.rows(), 10)

    def test_the_memo_and_quick_input_take_cut_this_way(self):
        source = open(app.__file__, encoding='utf-8').read()
        self.assertIn('self._install_safe_cut(self.editor)', source)
        self.assertIn('self._install_safe_cut(text)', source)


if __name__ == '__main__':
    unittest.main()
