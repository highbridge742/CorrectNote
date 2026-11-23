# -*- coding: utf-8 -*-
"""打鍵で隠したマウスの矢印を、マウスが動いていない <Motion>・<Leave>（新しい窓がマウスの下に出た・動いた時に Windows が
送るもの）では出し直さない（2026-11-23 うにさん 03:32「文字を打ってもマウスカーソルが非表示にならなかった」・03:37「再入力
変換の終了後に文字を打つとカーソルが消えない」・03:38「文末にカーソルを移動させてすぐ打つと、予測候補の影響でカーソルが
消えない」）。動いた時・押した時は今までどおり出し直す。CN_POINTER_STILL_MOTION=0 で前の形。
作った例だけ（本当のマウスは動かさない・窓は出さない）。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
from typing_pointer import TypingPointer


class StillMotion(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.text = tk.Text(self.root, cursor='xterm')
        self.text.pack()
        self.root.update()
        self.root.winfo_pointerxy = lambda: (300, 400)
        self.root.winfo_containing = lambda x, y, displayof=0: self.text

    def make(self):
        cls = app._still_typing_pointer(TypingPointer) if os.environ.get('CN_POINTER_STILL_MOTION') != '0' else TypingPointer
        p = cls(self.root, lambda: [self.text], lambda e: True)
        p.attach(self.text)
        return p

    def ev(self, kind, x, y):
        return NS(type=kind, x_root=x, y_root=y, widget=self.text)

    def test_still_motion_keeps_it_hidden(self):
        p = self.make()
        p.hide(self.text)
        self.assertEqual(str(self.text.cget('cursor')), 'none')
        p.restore(self.ev('6', 300, 400))                          # 動いていない Motion（窓が出ただけ）
        p.restore(self.ev('8', 300, 400))                          # 同じ所の Leave
        self.assertEqual(str(self.text.cget('cursor')), 'none')
        p.restore(self.ev('6', 301, 400))                          # 1px でも動いたら出す
        self.assertEqual(str(self.text.cget('cursor')), 'xterm')

    def test_press_still_shows_it(self):
        p = self.make()
        p.hide(self.text)
        p.restore(self.ev('4', 300, 400))                          # ButtonPress は今までどおり
        self.assertEqual(str(self.text.cget('cursor')), 'xterm')

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_POINTER_STILL_MOTION': '0'}):
            p = self.make()
            p.hide(self.text)
            p.restore(self.ev('6', 300, 400))
        self.assertEqual(str(self.text.cget('cursor')), 'xterm')    # 前の形: 動いていなくても出し直した


class OverPopup(StillMotion):
    """行末の予測の一覧（枠の無い小窓）がマウスの下に出ていても、打ったら隠す（CN_POINTER_HIDE_OVER_POPUP）。"""
    def setUp(self):
        super().setUp()
        self.pop = tk.Toplevel(self.root)
        self.pop.wm_overrideredirect(True)
        self.lb = tk.Listbox(self.pop, cursor='arrow')
        self.lb.pack()
        self.root.update()
        self.root.winfo_containing = lambda x, y, displayof=0: self.lb

    def test_still_motion_keeps_it_hidden(self):
        p = self.make()
        p.hide(self.text)
        self.assertEqual(str(self.text.cget('cursor')), 'none')
        self.assertEqual(str(self.lb.cget('cursor')), 'none')
        p.restore(self.ev('6', 300, 400))                          # 一覧が出し直されただけ
        self.assertEqual(str(self.lb.cget('cursor')), 'none')
        p.restore(self.ev('6', 305, 400))                          # 動いたら両方戻す
        self.assertEqual(str(self.text.cget('cursor')), 'xterm')
        self.assertEqual(str(self.lb.cget('cursor')), 'arrow')

    def test_press_still_shows_it(self):
        p = self.make()
        p.hide(self.text)
        p.restore(self.ev('4', 300, 400))
        self.assertEqual(str(self.lb.cget('cursor')), 'arrow')

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_POINTER_HIDE_OVER_POPUP': '0'}):
            p = self.make()
            p.hide(self.text)
        self.assertEqual(str(self.text.cget('cursor')), 'xterm')    # 前の形: 小窓の上では隠さなかった

    def test_framed_window_is_left_alone(self):
        self.pop.wm_overrideredirect(False)
        p = self.make()
        p.hide(self.text)
        self.assertEqual(str(self.text.cget('cursor')), 'xterm')    # 枠のある窓（辞書など）の上では今までどおり


if __name__ == '__main__':
    unittest.main()
