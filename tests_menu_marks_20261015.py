# -*- coding: utf-8 -*-
"""メニューの項目の見え方（2026-10-15）。

- チェック・ラジオの項目はラベルの左に透明な絵を置く（1文字目が欠けない）
- 横に開く項目（cascade）は右端に矢印の字を置く（うにさん「メニュー内の横に展開する
  アイコンが見えません」。Tk 8.6.9 は Windows 11 でこの矢印を描かない）
"""
import sys
import tkinter as tk
import unittest

import app


@unittest.skipUnless(sys.platform == 'win32', 'Windows のメニューだけ')
class MenuMarksTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.menu = tk.Menu(self.root, tearoff=0)
        self.sub = tk.Menu(self.menu, tearoff=0)

    def tearDown(self):
        self.root.destroy()

    def test_a_cascade_shows_an_arrow_in_the_menu_text_colour(self):
        self.menu.add_cascade(label='外見', menu=self.sub)
        self.menu.insert_cascade(0, label='配色', menu=self.sub)
        for i in (0, 1):
            self.assertEqual(self.menu.entrycget(i, 'accelerator'), app.MENU_CASCADE_ARROW)
            self.assertEqual(self.menu.entrycget(i, 'foreground'), '')   # the menu's own colour
        self.assertEqual(self.menu.entrycget(1, 'label'), '外見')        # label unchanged

    def test_the_arrow_follows_a_theme_change(self):
        self.menu.add_cascade(label='外見', menu=self.sub)
        self.menu.configure(fg='#e0e0e0', bg='#202020')
        self.assertEqual(self.menu.entrycget(0, 'foreground'), '')
        self.assertEqual(self.menu.entrycget(0, 'accelerator'), app.MENU_CASCADE_ARROW)

    def test_a_given_accelerator_is_kept(self):
        self.menu.add_cascade(label='x', menu=self.sub, accelerator='Ctrl+X')
        self.menu.add('cascade', {'label': 'y', 'menu': self.sub, 'accelerator': 'Y'})
        self.assertEqual(self.menu.entrycget(0, 'accelerator'), 'Ctrl+X')
        self.assertEqual(self.menu.entrycget(1, 'accelerator'), 'Y')

    def test_other_items_get_no_arrow_and_checks_keep_their_gap(self):
        self.menu.add_command(label='a')
        self.menu.add_checkbutton(label='UTF-8')
        self.menu.add_radiobutton(label='r')
        self.assertEqual(self.menu.entrycget(0, 'accelerator'), '')
        for i in (1, 2):
            self.assertEqual(self.menu.entrycget(i, 'accelerator'), '')
            self.assertTrue(str(self.menu.entrycget(i, 'image')))
            self.assertEqual(str(self.menu.entrycget(i, 'compound')), 'left')
        self.assertEqual(str(self.menu.entrycget(0, 'image')), '')


if __name__ == '__main__':
    unittest.main()
