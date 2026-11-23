# -*- coding: utf-8 -*-
"""狭い選択（半角1字など）をドラッグで掴みやすく（2026-11-23 うにさん「半角1文字をドラッグ移動しにくい。クリックできる
範囲を調整する」）。全角1字の幅より狭い1行の選択は、足りない幅の分だけ左右へ広げた所を「選択の上」とみなす。
それより外のクリックは今までどおり（奪わない）。ドラッグで移した後は選択を外す（CN_DRAG_DROP_DESELECT・同じ日の指定）。
CN_DRAG_GRAB_MIN_WIDTH=0・CN_DRAG_DROP_DESELECT=0 で前の形。自分の窓だけ。"""
import os
import tkinter as tk
import tkinter.font as tkfont
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import drag_move as D

TEXT = 'abc def ghi'


class FakeApp:
    def __init__(self):
        self._title_toc = None

    def _show_copy_frame(self, widget, start, end):
        pass

    def _clear_copy_emphasis(self):
        pass

    def _on_change(self, *a):
        pass


class GrabNarrow(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('600x200+40+40')
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root, undo=True, autoseparators=True, font=('Yu Gothic UI', 12))
        self.w.pack(fill='both', expand=True)
        self.w.insert('1.0', TEXT)
        self.w.edit_reset()
        self.d = D.install(FakeApp(), self.w)
        self.root.update()
        self.w.tag_add('sel', '1.4', '1.5')                     # 半角1字「d」
        self.box = self.w.bbox('1.4')
        self.full = tkfont.Font(font=self.w.cget('font')).measure('　')

    def press(self, x):
        self.d.state = None
        y = self.box[1] + self.box[3] // 2
        got = self.d.press(NS(x=x, y=y, state=0))
        state = self.d.state
        self.d.state = None
        self.d._cancel_timer()
        return state

    def test_narrow_selection_is_wider_to_grab(self):
        x0, w = self.box[0], self.box[2]
        self.assertLess(w, self.full)
        pad = (self.full - w) / 2.0
        self.assertEqual(self.press(x0 + w // 2), 'armed')                 # 字の上
        self.assertEqual(self.press(int(x0 - pad + 1)), 'armed')           # 左へ広げた所
        self.assertEqual(self.press(int(x0 + w + pad - 1)), 'armed')       # 右へ広げた所
        self.assertIsNone(self.press(int(x0 - pad - 3)))                    # その外は今までどおり（奪わない）
        self.assertIsNone(self.press(int(x0 + w + pad + 3)))

    def test_switch_back(self):
        x0, w = self.box[0], self.box[2]
        pad = (self.full - w) / 2.0
        with mock.patch.dict(os.environ, {'CN_DRAG_GRAB_MIN_WIDTH': '0'}):
            self.assertIsNone(self.press(int(x0 - pad + 1)))               # 前の形: 字の外は掴めない

    def test_wide_selection_is_unchanged(self):
        self.w.tag_remove('sel', '1.0', 'end')
        self.w.tag_add('sel', '1.0', '1.7')                                # 全角1字より広い
        a = self.w.bbox('1.0')
        self.assertIsNone(self.press(a[0] - 3))


class Deselect(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root, undo=True)
        self.w.insert('1.0', TEXT)
        self.d = D.DragMove(NS(), self.w, on_change=None, body=False)

    def drop(self):
        self.w.tag_add('sel', '1.0', '1.4')
        self.d.sel = ('1.0', '1.4')
        self.assertTrue(self.d.drop('1.11'))

    def test_deselected_after_drop(self):
        self.drop()
        self.assertEqual(self.w.get('1.0', 'end-1c'), 'def ghiabc ')
        self.assertFalse(self.w.tag_ranges('sel'))
        self.assertEqual(self.w.index('insert'), '1.11')                   # 落とした範囲の終わり

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_DRAG_DROP_DESELECT': '0'}):
            self.drop()
        self.assertEqual(self.w.get('sel.first', 'sel.last'), 'abc ')       # 前の形: 落とした範囲を選んだまま


if __name__ == '__main__':
    unittest.main()
