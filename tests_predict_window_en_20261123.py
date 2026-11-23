# -*- coding: utf-8 -*-
"""予測のカスタム編集の窓（f5_predict_window）を英語で開いた時（2026-11-23 11:11 うにさん「英語で動いている場合、カスタム
画面開始時に半角を開く。全角の切り替えボタンには日本語向けと書く。日本語言語では現状のまま」）。
・英語: 開いた時は半角時の一覧。全角時のボタンは「Full-width input (for Japanese)」
・日本語: 開いた時は全角時の一覧・文言も今のまま
・言語を切り替えた後に開いた時も、その時の言語で決まる
CN_PREDICT_WINDOW_EN=0 で前の形。自分の窓だけ。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import f5_predict
import f5_predict_window as FW
import ui_lang


class WindowLanguage(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.addCleanup(ui_lang.set_language, 'ja')
        store = {}
        self.app = NS(root=self.root, settings=NS(get=lambda k: store.get(k), set=lambda k, v: store.__setitem__(k, v),
                                                  save=lambda: None))

    def shown(self, kind):
        dlg = FW.open_window(self.app, kind)
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        f = dlg._f5
        texts = []
        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() == 'Radiobutton':
                    texts.append(str(c.tk.call(c._w, 'cget', '-text')))       # 画面に出ている字（訳した後）
                walk(c)
        walk(dlg)
        got = (f['which'].get(), texts, list(f['listbox'].get(0, 'end')))
        dlg.destroy()
        return got

    def test_english_opens_half_width_and_says_for_japanese(self):
        ui_lang.set_language('en')
        for kind in ('head', 'end'):
            which, texts, items = self.shown(kind)
            self.assertEqual(which, kind + '_narrow', texts)
            self.assertEqual(items, [FW.marked(c) for c in f5_predict.default_list(kind + '_narrow')])
            self.assertEqual(texts[0], 'Full-width input (for Japanese)', texts)
            self.assertEqual(texts[1], 'Half-width input', texts)

    def test_japanese_is_unchanged(self):
        ui_lang.set_language('ja')
        which, texts, items = self.shown('head')
        self.assertEqual(which, 'head_wide')
        self.assertEqual(texts, ['全角時', '半角時'])

    def test_switching_language_then_opening(self):
        ui_lang.set_language('en')
        self.assertEqual(self.shown('end')[0], 'end_narrow')
        ui_lang.set_language('ja')
        self.assertEqual(self.shown('end')[0], 'end_wide')
        ui_lang.set_language('en')
        self.assertEqual(self.shown('end')[0], 'end_narrow')

    def test_switch_back(self):
        ui_lang.set_language('en')
        with mock.patch.dict(os.environ, {'CN_PREDICT_WINDOW_EN': '0'}):
            which, texts, items = self.shown('head')
        self.assertEqual(which, 'head_wide')                                     # 前の形
        self.assertEqual(texts[0], 'Full-width input')


if __name__ == '__main__':
    unittest.main()
