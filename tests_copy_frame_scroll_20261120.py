# -*- coding: utf-8 -*-
"""コピーした範囲の白い枠は、スクロールしたら消える（2026-11-20 うにさん「範囲をコピーした時の白い枠が、スクロール
しても消えない時があった」）。
1) 本文の中のタイトル・目次が上に見えている間は、左上の字の位置がいつも 1.0 で、スクロールを「動いていない」と見ていた
2) ドラッグで移す時の枠（drag_move）は、スクロールで消える印を立てていなかった
自分の Tk の窓だけ・作った例文。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import title_inline as TI


class CopyFrameScroll(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('500x300+40+40')
        self.w = tk.Text(self.root, font=('Meiryo', 11))
        self.w.pack(fill='both', expand=True)
        TI.prepare(self.w)
        TI.style(self.w, 'Meiryo', 10, '#1f5fbf', '#888888')
        TI.write(self.w, '試しの題', [(2, 2, '二行目'), (4, 4, '四行目')])
        self.w.insert('1.0', '\n'.join('%d行目の本文です。' % i for i in range(1, 80)))
        self.w.yview_moveto(0)
        self.root.update()
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.COPY_EMPHASIS_PERCENT = 100
        self.a._copy_emphasis = None
        self.a._copy_frame = None

    def tearDown(self):
        try:
            self.a._clear_copy_emphasis()
        except Exception:
            pass
        self.root.destroy()

    def shown(self):
        frame = getattr(self.a, '_copy_frame', None)
        return bool(frame is not None and frame.lines)

    def test_scroll_under_the_title_clears_the_frame(self):
        self.a._show_copied(self.w, '1.0', '1.3')
        self.assertTrue(self.shown())
        self.assertEqual(self.w.index('@0,0'), '1.0')               # タイトルが上に見えている
        self.w.yview_scroll(1, 'units')                                # 見出しの中で少しだけ送る
        self.root.update()
        self.assertEqual(self.w.index('@0,0'), '1.0')               # 本文の位置ではまだ 1.0
        self.a._copy_emphasis_scrolled(self.w)
        self.assertFalse(self.shown())

    def test_no_scroll_keeps_the_frame(self):
        self.a._show_copied(self.w, '1.0', '1.3')
        self.a._copy_emphasis_scrolled(self.w)
        self.assertTrue(self.shown())

    def test_drag_frame_is_cleared_by_scroll_but_not_while_dragging(self):
        self.a._show_copy_frame(self.w, '2.0', '2.3')                 # drag_move と同じ道（印を立てない）
        self.w._cn_drag_move = NS(state='dragging')
        self.a._copy_emphasis_scrolled(self.w)
        self.assertTrue(self.shown())                                  # 移している最中は消さない
        self.w._cn_drag_move = NS(state=None)
        self.a._copy_emphasis_scrolled(self.w)
        self.assertFalse(self.shown())

    def test_switch_back(self):
        self.a._show_copied(self.w, '1.0', '1.3')
        self.w.yview_scroll(1, 'units')
        self.root.update()
        with mock.patch.dict(os.environ, {'CN_COPY_FRAME_YVIEW': '0'}):
            self.a._copy_emphasis_scrolled(self.w)
        self.assertTrue(self.shown())                                  # 前の動き: 消えなかった


if __name__ == '__main__':
    unittest.main()
