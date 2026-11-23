# -*- coding: utf-8 -*-
"""再入力変換を抜けた時のマウスの矢印（2026-11-23 10:05 うにさん「再入力変換から抜けた時にカーソルが戻って消えません」）。
・抜けただけでマウスが動いていなければ、出し直さない（隠したまま打鍵側へ渡し、動かせば戻る）
・抜けた後に打てば消える（打鍵側が「隠している」と思い込んで隠さない食い違いを残さない）
・マウスが動いて出し直した時は、打鍵側の覚えも消す
CN_REINPUT_POINTER_HANDOFF=0 で前の形。作った例だけ（本当のマウスは動かさない・窓は出さない）。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import reinput
from typing_pointer import TypingPointer


class Handoff(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.text = tk.Text(self.root, cursor='xterm')
        self.text.pack()
        self.root.update()
        self.xy = [300, 400]
        for w in (self.root, self.text):
            w.winfo_pointerxy = lambda: tuple(self.xy)
            w.focus_get = lambda: self.text
        self.root.winfo_containing = lambda x, y, displayof=0: self.text
        self.mode = NS(state='busy')
        self.fake = NS(editor=self.text, result_view=None, _quick_text=None, _dropdown=None, _f2_focus_target=None,
                       _reinput=self.mode, _quick_reinput=None, root=self.root)

    def make(self):
        pcls = app._still_typing_pointer(TypingPointer)
        self.pointer = pcls(self.root, lambda: [self.text], lambda e: True)
        self.pointer.attach(self.text)
        self.fake._typing_pointer = self.pointer
        if os.environ.get('CN_REINPUT_POINTER_HANDOFF') == '0':
            hider = reinput.CursorHider(self.fake)
        else:
            hider = app._handoff_cursor_hider(reinput.CursorHider)(self.fake)
        self.addCleanup(hider.restore)
        return hider

    def cursor(self):
        return str(self.text.cget('cursor'))

    def motion(self, x, y):
        self.pointer.restore(NS(type='6', x_root=x, y_root=y, widget=self.text))

    def test_leaving_without_moving_keeps_it_hidden(self):
        hider = self.make()
        hider.hide()                                 # 再入力変換のキー操作
        self.assertEqual(self.cursor(), 'none')
        self.mode.state = None                       # 抜けた
        hider.check()
        self.assertEqual(self.cursor(), 'none')      # 出し直さない
        self.motion(300, 400)                        # 窓が閉じただけの動いていない Motion
        self.assertEqual(self.cursor(), 'none')
        self.motion(306, 400)                        # 動かしたら戻る
        self.assertEqual(self.cursor(), 'xterm')
        self.pointer.hide(self.text)                 # その後に打てば消える
        self.assertEqual(self.cursor(), 'none')

    def test_typing_after_a_move_hides_again(self):
        hider = self.make()
        self.pointer.hide(self.text)                 # 打鍵側が先に隠していた
        hider.hide()
        self.xy[:] = [320, 400]                      # 動いてから抜けた
        self.mode.state = None
        hider.check()
        self.assertEqual(self.cursor(), 'xterm')
        self.assertEqual(self.pointer.saved, {})     # 打鍵側の「隠している」も消えた
        self.pointer.hide(self.text)
        self.assertEqual(self.cursor(), 'none')      # 打てば消える

    def test_stale_typing_memory_does_not_block_hiding(self):
        self.make()
        self.pointer.hide(self.text)
        self.text.configure(cursor='xterm')          # 別の道で出し直された（打鍵側は知らない）
        self.pointer.hide(self.text)
        self.assertEqual(self.cursor(), 'none')

    def test_focus_leaving_still_shows_it(self):
        hider = self.make()
        hider.hide()
        self.mode.state = None
        self.text.focus_get = lambda: None           # アプリの外へ
        hider.check()
        self.assertEqual(self.cursor(), 'xterm')

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_REINPUT_POINTER_HANDOFF': '0'}):
            hider = self.make()
            self.pointer.hide(self.text)
            hider.hide()
            self.mode.state = None
            hider.check()
            self.assertEqual(self.cursor(), 'xterm')     # 前の形: 動いていなくても出し直した
            self.pointer.hide(self.text)
            self.assertEqual(self.cursor(), 'xterm')     # 前の形: 打鍵側は隠しているつもりで隠さなかった


if __name__ == '__main__':
    unittest.main()
