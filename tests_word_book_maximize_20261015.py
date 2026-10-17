# -*- coding: utf-8 -*-
"""単語帳の窓は最大化しない（2026-10-15 うにさん「単語帳をドラッグしてウインドウの最上部に触れても、
最大化されないようにする。できれば単語帳ウインドウから最大化ボタンを消す」）。

一時フォルダの作った単語帳だけを使う（本人の word_book.json は読まない）。
"""
import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import word_book
from word_book import WordBook


@unittest.skipUnless(os.name == 'nt', 'Windows の窓の印')
class WordBookMaximizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'word_book.json'
        self.path.write_text(json.dumps({'version': 2, 'sets': [['一', '二'], [], [], []], 'active_set': 0,
                                         'visible': False, 'width': 220}, ensure_ascii=False), encoding='utf-8')
        self.root = tk.Tk()
        self.root.geometry('300x200+40+40')
        self.colors = ['#ffffff', '#000000', '#3366cc']
        self.app = SimpleNamespace(root=self.root, status=Mock(), word_book_btn=Mock(),
                                   _editor_font=lambda: ('Yu Gothic UI', 10),
                                   _start_word_book_add=lambda: None, _pick_mode=None,
                                   _set_window_icons_win32=lambda win: None)
        placing = patch.object(WordBook, '_place', lambda book: book.window.geometry('+420+120'))
        placing.start()
        self.addCleanup(placing.stop)
        self.book = WordBook(self.app, self.path, lambda: tuple(self.colors), lambda: 220)
        self.book.open()
        self.settle()

    def tearDown(self):
        try:
            self.book.close()
        except Exception:
            pass
        self.root.destroy()
        self.tmp.cleanup()

    def settle(self):
        for _ in range(5):
            self.root.update()

    def style(self):
        return word_book._frame_style(self.book.window)

    def assert_no_maximize(self):
        style = self.style()
        self.assertIsNotNone(style)
        self.assertFalse(style & word_book.WS_MAXIMIZEBOX, hex(style))
        self.assertTrue(style & word_book.WS_THICKFRAME, hex(style))     # 大きさは変えられる
        self.assertTrue(style & word_book.WS_MINIMIZEBOX, hex(style))    # 最小化はできる

    def test_the_window_has_no_maximize_button(self):
        self.assert_no_maximize()

    def test_reopened_and_restored_and_recoloured_stay_without_it(self):
        self.book.close()
        self.settle()
        self.book.open()
        self.settle()
        self.assert_no_maximize()
        self.book.window.iconify()
        self.settle()
        self.book.window.deiconify()
        self.settle()
        self.assert_no_maximize()
        self.colors[:] = ['#202020', '#e0e0e0', '#88aaff']         # 配色の切り替え（単語帳は塗り直すだけ）
        self.book.render()
        self.settle()
        self.assert_no_maximize()

    def test_tk_rebuilding_the_frame_style_is_undone(self):
        # wm resizable で Tk が枠の印を作り直すと最大化ボタンが戻ることがある → 次の Configure で外す
        self.book.window.resizable(True, False)
        self.book.window.geometry('%dx%d' % (self.book.window.winfo_width() + 10, self.book.window.winfo_height()))
        self.settle()
        self.assert_no_maximize()

    def test_zoomed_returns_to_normal(self):
        before = self.book.window.winfo_width()
        self.book.window.state('zoomed')
        self.settle()
        self.assertEqual(self.book.window.state(), 'normal')
        self.assertLess(self.book.window.winfo_width(), self.root.winfo_screenwidth() - 50)
        self.assertLessEqual(abs(self.book.window.winfo_width() - before), 40)


if __name__ == '__main__':
    unittest.main()
