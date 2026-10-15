# -*- coding: utf-8 -*-
"""単語帳の並べ替え（2026-10-15 うにさん）: 右クリックの「ひとつ上と入れ替え」と左ドラッグ。

一時フォルダの作った単語帳だけを使う（本人の word_book.json は読まない）。
"""
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import word_book
from word_book import WordBook


class WordBookOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'word_book.json'
        self.path.write_text(json.dumps({'version': 2, 'sets': [['一', '二', '三', '四'], [], [], []],
                                         'active_set': 0, 'visible': False, 'width': 220},
                                        ensure_ascii=False), encoding='utf-8')
        self.root = tk.Tk()
        self.root.geometry('300x200+40+40')
        self.copied = []
        app = SimpleNamespace(root=self.root, status=Mock(), word_book_btn=Mock(),
                              _editor_font=lambda: ('Yu Gothic UI', 10),
                              _start_word_book_add=lambda: None, _pick_mode=None,
                              _set_window_icons_win32=lambda win: None)
        self.app = app
        placing = patch.object(WordBook, '_place', lambda book: None)   # 本体の窓の横に置く所は見ない
        placing.start()
        self.addCleanup(placing.stop)
        self.book = WordBook(app, self.path, lambda: ('#ffffff', '#000000', '#3366cc'), lambda: 220)
        self.book.copy = lambda text: self.copied.append(text)
        self.book.open()
        self.book.render()      # buttons now call the patched copy
        self.book.window.geometry('+400+80')
        self.root.update()

    def tearDown(self):
        try:
            self.book.close()
        except Exception:
            pass
        self.root.destroy()
        self.tmp.cleanup()

    def saved(self):
        return json.loads(self.path.read_text(encoding='utf-8'))['sets'][0]

    def menu_labels(self, index):
        captured = {}

        def popup(menu, x, y):
            captured['menu'] = menu
        with patch.object(tk.Menu, 'tk_popup', lambda menu, x, y: popup(menu, x, y)):
            self.book.remove_menu(SimpleNamespace(x_root=0, y_root=0), index)
        menu = captured['menu']
        return menu, {menu.entrycget(i, 'label'): str(menu.entrycget(i, 'state'))
                      for i in range(menu.index('end') + 1)}

    def test_swap_with_the_one_above_from_the_menu(self):
        menu, labels = self.menu_labels(2)
        self.assertEqual(labels['ひとつ上と入れ替え'], 'normal')
        menu.invoke(menu.index('ひとつ上と入れ替え'))
        self.assertEqual(self.book.words, ['一', '三', '二', '四'])
        self.assertEqual(self.saved(), ['一', '三', '二', '四'])     # 保存に残る
        self.assertEqual([b.cget('text') for b in self.book.buttons], ['一', '三', '二', '四'])
        # いちばん上では押せない
        menu, labels = self.menu_labels(0)
        self.assertEqual(labels['ひとつ上と入れ替え'], 'disabled')
        self.assertEqual(labels['消す'], 'normal')

    def test_the_order_survives_a_restart(self):
        self.book.move(3, 0)
        again = WordBook(self.app, self.path, self.book.colors, lambda: 220)
        self.assertEqual(again.sets[0], ['四', '一', '二', '三'])

    def drag(self, index, to_row, cancel=False, outside=False):
        b = self.book.buttons[index]
        x = b.winfo_rootx() + 10
        y0 = b.winfo_rooty() + b.winfo_height() // 2
        rows = [bb.master for bb in self.book.buttons]
        if outside:
            y1 = self.book.canvas.winfo_rooty() + self.book.canvas.winfo_height() + 80
        else:
            r = rows[to_row]
            y1 = r.winfo_rooty() + (r.winfo_height() - 3 if to_row > index else 2)
        b.event_generate('<ButtonPress-1>', x=10, y=5, rootx=x, rooty=y0)
        for y in (y0 + (2 if y1 > y0 else -2), (y0 + y1) // 2, y1):
            b.event_generate('<B1-Motion>', x=10, y=5, rootx=x, rooty=y, state=0x100)
            self.root.update()
        line = getattr(self.book, '_order_line', None)
        shown = bool(line is not None and line.winfo_exists() and line.winfo_ismapped())
        if cancel:
            self.book._order_cancel()
        b.event_generate('<ButtonRelease-1>', x=10, y=5, rootx=x, rooty=y1)
        self.root.update()
        return shown

    def test_drag_down_and_up(self):
        self.assertTrue(self.drag(0, 2))              # 入る場所の線が出る
        self.assertEqual(self.book.words, ['二', '三', '一', '四'])
        self.drag(3, 0)
        self.assertEqual(self.book.words, ['四', '二', '三', '一'])
        self.assertEqual(self.saved(), ['四', '二', '三', '一'])
        self.assertEqual(self.copied, [])             # 並べ替えではコピーしない
        line = getattr(self.book, '_order_line', None)
        self.assertFalse(line is not None and line.winfo_exists() and line.winfo_ismapped())

    def test_escape_or_outside_keeps_the_order(self):
        self.drag(0, 3, cancel=True)
        self.drag(1, 3, outside=True)
        self.assertEqual(self.book.words, ['一', '二', '三', '四'])
        self.assertEqual(self.saved(), ['一', '二', '三', '四'])
        self.assertEqual(self.copied, [])

    def test_a_small_wobble_is_still_a_click(self):
        b = self.book.buttons[1]
        x, y = b.winfo_rootx() + 10, b.winfo_rooty() + 5
        b.event_generate('<Enter>', x=10, y=5)
        b.event_generate('<ButtonPress-1>', x=10, y=5, rootx=x, rooty=y)
        b.event_generate('<B1-Motion>', x=12, y=7, rootx=x + 2, rooty=y + 2, state=0x100)
        b.event_generate('<ButtonRelease-1>', x=12, y=7, rootx=x + 2, rooty=y + 2)
        self.root.update()
        self.assertEqual(self.copied, ['二'])
        self.assertEqual(self.book.words, ['一', '二', '三', '四'])


if __name__ == '__main__':
    unittest.main()
