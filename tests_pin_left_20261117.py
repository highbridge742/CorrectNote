# -*- coding: utf-8 -*-
"""本文の欄・補正欄を左端に留める（2026-11-17 うにさん「起動時、1文字目の表示が消えています」）。欄は折り返すが、
折り返さない長い行（text_links の literal_no_wrap）の行末を見せると、Tk が欄を横へ送り、どの行も1字目が隠れた。
自分の Tk の窓だけ・作った例文。"""
import tkinter as tk
import unittest

import app


class PinLeft(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('400x200+40+40')

    def tearDown(self):
        self.root.destroy()

    def pane(self, pin):
        t = tk.Text(self.root, wrap='word', width=30, height=6)
        t.pack(fill='both', expand=True)
        t.tag_configure('literal_no_wrap', wrap='none')
        t.insert('1.0', '誤変換の佑から着手。\n' + '長い行' * 400 + '\n三行目')
        t.tag_add('literal_no_wrap', '2.0', '2.end')
        if pin:
            app._pin_left(t)
        self.root.update()
        t.mark_set('insert', '2.end')
        t.see('insert')
        self.root.update()
        self.root.update()
        return t

    def test_view_returns_to_the_left_edge(self):
        t = self.pane(True)
        self.assertEqual(float(t.xview()[0]), 0.0)

    def test_without_the_pin_the_view_moved(self):
        t = self.pane(False)
        self.assertGreater(float(t.xview()[0]), 0.0)          # 前の動き: 横に送られたまま（1字目が隠れる）


if __name__ == '__main__':
    unittest.main()
