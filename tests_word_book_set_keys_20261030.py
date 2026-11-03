# -*- coding: utf-8 -*-
"""単語帳の窓が前にあるとき、数字キー 1〜4（テンキーも）でセットを切り替える（2026-10-30 うにさん）。

一時フォルダの作った単語帳だけを使う（本人の word_book.json は読まない）。窓は焦点を取らせない。
"""
import json
import re
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from word_book import WordBook


class WordBookSetKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'word_book.json'
        self.path.write_text(json.dumps({'version': 2, 'sets': [['一'], ['二'], ['三'], ['四']],
                                         'active_set': 0, 'visible': False, 'width': 220},
                                        ensure_ascii=False), encoding='utf-8')
        self.root = tk.Tk()
        self.root.withdraw()
        app = SimpleNamespace(root=self.root, status=Mock(), word_book_btn=Mock(),
                              _editor_font=lambda: ('Yu Gothic UI', 10),
                              _start_word_book_add=lambda: None, _pick_mode=None,
                              _set_window_icons_win32=lambda win: None)
        placing = patch.object(WordBook, '_place', lambda book, near_pointer=False: None)
        placing.start()
        self.addCleanup(placing.stop)
        self.book = WordBook(app, self.path, lambda: ('#ffffff', '#000000', '#3366cc'), lambda: 220)
        self.book.open()
        self.book.window.geometry('+10000+100')
        self.root.update()

    def tearDown(self):
        try:
            self.book.close()
        except Exception:
            pass
        self.root.destroy()
        self.tmp.cleanup()

    def test_number_keys_and_keypad_choose_the_set(self):
        win = self.book.window
        for index, keys in enumerate(WordBook.SET_KEYS):
            for key in keys:
                with self.subTest(key=key):
                    script = win.bind('<KeyPress-%s>' % key)
                    self.assertTrue(script)
                    self.book.active_set = (index + 1) % 4
                    # the bound script with its %-fields filled in, as Tk runs it (it ends in break)
                    win.tk.eval('foreach _ 1 {%s}' % re.sub('%.', '0', script))
                    self.assertEqual(self.book.active_set, index)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['active_set'], 3)
        self.assertIn('セット4', win.title())


if __name__ == '__main__':
    unittest.main()
