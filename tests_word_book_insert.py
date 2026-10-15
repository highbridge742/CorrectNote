"""単語帳のボタンで、直前に焦点のあった欄へ文字を入れる（2026-10-14 うにさん）。

コピーは今まで通りに行い、そのうえで
・CorrectNote 自身の欄（メモ欄・検索欄など）なら Tk の打ち込みで入れる
・別のアプリの窓なら、焦点の欄が文字の欄のときだけ Ctrl+V を送る
・文字の欄でなければ何もしない（コピーだけ）。Enter は送らない。
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tkinter as tk

import app
import word_book
from word_book import WordBook


class _Native:
    def __init__(self, user, previous=None, restored=True):
        self.user = user
        self.previous = previous
        self.restored = restored
        self.paste = Mock(return_value=True)

    def restore_previous(self):
        return self.restored

    def detach(self):
        pass


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class WordBookInsertTest(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('300x200+40+40')
        self.text = tk.Text(self.root)
        self.text.pack()
        self.entry = tk.Entry(self.root)
        self.entry.pack()
        self.root.update()
        import ctypes
        from ctypes import wintypes as W
        user = ctypes.WinDLL('user32')
        user.GetAncestor.argtypes = [W.HWND, W.UINT]
        user.GetAncestor.restype = W.HWND
        self.hwnd = user.GetAncestor(self.root.winfo_id(), 2)
        self.user = SimpleNamespace(GetAncestor=user.GetAncestor,
                                    GetForegroundWindow=lambda: self.hwnd)
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.status = tk.Label(self.root)
        self.a = a
        self.book = WordBook.__new__(WordBook)
        self.book.app = a
        self.book.window = None
        self.book._focus_job = self.book._insert_job = None
        self.book._pending_text = None
        self.focused = None

    def _focus(self, widget):
        # A test window need not hold the OS focus, so Tk may not record
        # the focus; stand in for "the field that last had it".
        widget.focus_set()
        self.focused = widget

    def _other_front(self, hwnd=0x1234):
        return SimpleNamespace(GetAncestor=self.user.GetAncestor,
                               GetForegroundWindow=lambda: hwnd)

    def tearDown(self):
        self.root.destroy()

    def _run(self, native, text='単語帳😀'):
        self.book._native = native
        last = self.root if self.focused is None else self.focused
        with patch.object(self.root, 'clipboard_clear'), \
                patch.object(self.root, 'clipboard_append') as append, \
                patch.object(tk.Tk, 'focus_lastfor', return_value=last):
            self.book.copy(text)
            for _ in range(100):
                self.root.update()
                if self.book._focus_job is None and self.book._insert_job is None:
                    break
                self.root.after(10)
        append.assert_called_once_with(text)
        self.assertIsNone(self.book._insert_job)

    def test_memo_gets_the_word_at_the_caret(self):
        self.text.insert('1.0', 'あいう')
        self.text.mark_set('insert', '1.1')
        self._focus(self.text)
        self.root.update()
        native = _Native(self.user, (self.hwnd, os.getpid()))
        self._run(native)
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'あ単語帳😀いう')
        native.paste.assert_not_called()
        self.assertIn('入れました', self.a.status.cget('text'))

    def test_selection_is_replaced_and_no_newline(self):
        self.text.insert('1.0', 'abc')
        self.text.tag_add('sel', '1.1', '1.2')
        self.text.mark_set('insert', '1.2')
        self._focus(self.text)
        self.root.update()
        self._run(_Native(self.user, (self.hwnd, os.getpid())), 'XY')
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'aXYc')

    def test_entry_of_the_app_too(self):
        self._focus(self.entry)
        self.root.update()
        self._run(_Native(self.user, (self.hwnd, os.getpid())), '語')
        self.assertEqual(self.entry.get(), '語')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '')

    def test_readonly_or_non_text_field_only_copies(self):
        self.text.configure(state='disabled')
        self._focus(self.text)
        self.root.update()
        self._run(_Native(self.user, (self.hwnd, os.getpid())))
        self.assertEqual(self.a.status.cget('text'), '単語帳の文字をコピーしました')

    def test_app_not_in_front_is_left_alone(self):
        self._focus(self.text)
        self.root.update()
        user = SimpleNamespace(GetAncestor=self.user.GetAncestor,
                               GetForegroundWindow=lambda: 0)
        self._run(_Native(user, (self.hwnd, os.getpid())))
        self.assertEqual(self.text.get('1.0', 'end-1c'), '')

    def test_other_app_gets_ctrl_v(self):
        native = _Native(self._other_front(), (0x1234, os.getpid() + 1))
        self._run(native)
        native.paste.assert_called_once_with(0x1234)
        self.assertEqual(self.text.get('1.0', 'end-1c'), '')
        self.assertIn('入れました', self.a.status.cget('text'))

    def test_other_app_without_text_box_only_copies(self):
        native = _Native(self._other_front(), (0x1234, os.getpid() + 1))
        native.paste.return_value = False
        self._run(native)
        self.assertEqual(self.a.status.cget('text'), '単語帳の文字をコピーしました')

    def test_waits_until_the_window_has_settled(self):
        # Foreground not handed over yet, then activation not finished:
        # ask again instead of giving up (seen on the real EDIT peer).
        fronts = iter([0, 0x1234, 0x1234, 0x1234])
        user = SimpleNamespace(GetAncestor=self.user.GetAncestor,
                               GetForegroundWindow=lambda: next(fronts, 0x1234))
        native = _Native(user, (0x1234, os.getpid() + 1))
        native.paste.side_effect = [None, True]
        self._run(native)
        self.assertEqual(native.paste.call_count, 2)
        self.assertIn('入れました', self.a.status.cget('text'))

    def test_third_window_in_front_stops_waiting(self):
        user = SimpleNamespace(GetAncestor=self.user.GetAncestor,
                               GetForegroundWindow=lambda: 0x9999)
        native = _Native(user, (0x1234, os.getpid() + 1))
        self._run(native)
        native.paste.assert_not_called()

    def test_window_not_given_back_inserts_nothing(self):
        native = _Native(self._other_front(), (0x1234, os.getpid() + 1), restored=False)
        self._run(native)
        native.paste.assert_not_called()

    def test_paste_needs_a_focused_text_box(self):
        # The real native helper: Ctrl+V is never sent unless the window is
        # in front with a caret or an edit-class control focused.
        native = word_book._WordBookNative.__new__(word_book._WordBookNative)
        native.c = __import__('ctypes')
        native.user = SimpleNamespace(GetForegroundWindow=lambda: 0)
        with patch('quick_return._user') as user:
            self.assertFalse(native.paste(0x1234))
            user.return_value.keybd_event.assert_not_called()


if __name__ == '__main__':
    unittest.main()
