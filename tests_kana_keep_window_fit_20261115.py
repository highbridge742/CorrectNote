# -*- coding: utf-8 -*-
"""ひらがなのまま通す語の窓の大きさ（2026-11-15 うにさん「ひらがなのままのウィンドウの下のボタンが見切れている。デフォルトで
縦に伸ばすが、手動で縮めた時もボタンを見切れさせない。項目が少ない時は縦を縮める。（初めから）の表示は要らない」）。
自分の試験の窓だけ（キー送り・クリップボードは使わない）。語の一覧は一時フォルダ（本人のファイルには触らない）。"""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

import kana_keep_list
import kana_keep_window
from tests_kana_keep_window_20261114 import _Folder, _Settings


class Fit(_Folder):
    def setUp(self):
        super().setUp()
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        # 窓は本体の窓に付く（transient）ので、本体を隠すと出ない。小さく出しておく
        self.root.geometry('120x60+700+40')
        self.app = SimpleNamespace(root=self.root, settings=_Settings(), kana_keep_changed=mock.Mock(),
                                   _place_dialog=lambda w, a, b: w.geometry('%dx%d+40+20' % (a, b)))

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        super().tearDown()

    def open(self):
        self.w = kana_keep_window.KanaKeepWindow(self.app)
        win = self.w.open()
        self.root.update()
        return win

    def buttons_inside(self, win):
        bottom = self.w.apply_button.master
        return bottom.winfo_y() + bottom.winfo_height() <= win.winfo_height()

    def test_buttons_are_seen_when_shrunk_by_hand(self):
        win = self.open()
        self.assertTrue(self.buttons_inside(win))
        low = win.minsize()[1]
        win.geometry('%dx%d' % (kana_keep_window.KanaKeepWindow.WIDTH, low))
        self.root.update()
        self.assertTrue(self.buttons_inside(win))
        self.assertGreaterEqual(self.w.canvas.winfo_height(), 20)       # 一覧は残りでスクロール

    def test_few_words_make_a_short_window(self):
        for word in list(kana_keep_list.words()):
            kana_keep_list.remove_word(word)
        kana_keep_list.add_word('すてき')
        win = self.open()
        self.assertLess(win.winfo_height(), win.winfo_screenheight() - kana_keep_window.KanaKeepWindow.SCREEN_MARGIN)
        self.assertTrue(self.buttons_inside(win))
        # 一覧の外＋一覧の最小の高さより少しだけ高い（語1つぶん）
        self.assertLessEqual(win.winfo_height(), win.minsize()[1] + 60)

    def test_many_words_stretch_to_the_screen(self):
        for i in range(120):
            kana_keep_list.add_word('ためしのご' + 'あいうえおかきくけこさしすせそ'[i % 15] + str(i))
        win = self.open()
        limit = win.winfo_screenheight() - kana_keep_window.KanaKeepWindow.SCREEN_MARGIN
        self.assertLessEqual(win.winfo_height(), limit)
        self.assertGreater(win.winfo_height(), 500)
        self.assertTrue(self.buttons_inside(win))
        self.assertLessEqual(win.winfo_y() + win.winfo_height(), limit + 40)

    def test_the_bundled_list_fits_the_screen(self):
        """同梱の語（2026-11-15 batch573 で約130語）のままでも、窓は画面に収まり、ボタンが見える。"""
        self.assertGreater(len(kana_keep_list.entries()), 100)
        win = self.open()
        limit = win.winfo_screenheight() - kana_keep_window.KanaKeepWindow.SCREEN_MARGIN
        self.assertLessEqual(win.winfo_height(), limit)
        self.assertTrue(self.buttons_inside(win))
        self.assertGreater(self.w.canvas.winfo_height(), 50)

    def test_no_built_in_mark(self):
        self.open()
        texts = []
        for row in self.w.words_frame.winfo_children():
            texts.extend(child.cget('text') for child in row.winfo_children() if 'text' in child.keys())
        self.assertFalse(any('初めから' in str(t) or 'built-in' in str(t) for t in texts))


if __name__ == '__main__':
    unittest.main()
