# -*- coding: utf-8 -*-
"""打ったばかりの語を選んで F6（ひらがな）・F7〜F9 にする時、打鍵の記録（打ったキー）から作ったかなを使う（2026-11-23
03:32 うにさん「入力したばかりの単語を範囲選択してF6したら、別の読みになった。打ったキーの文字にする」）。範囲が打った
確定で丸ごと埋まっていない・かなにならない時は今までどおり形態素の読み。CN_F6_FROM_KEYS=0 で前の形。
作った字・作った打鍵だけ。Tk の窓は出さない。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import ime_watch
import reinput


def make_reinput(records):
    r = reinput.ReInput.__new__(reinput.ReInput)
    r.app = NS(store=NS(_tokenize_fn=lambda line: []), ime_readings=None, dict_index=None,
               settings={'input_method': 'kana'})
    r.quick = False
    r._line_readings = lambda row: list(records)
    r._reverse = lambda text: None
    return r


class F6FromKeys(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        self.w.insert('1.0', '前の字 一が動く')
        # 「一が動く」を打った確定。IME の読みは「いつがうごく」（取り違え）、打ったキーは い ち か゛ う こ゛ く
        keys = tuple((k, i) for i, k in enumerate('eat@4b@h'))
        rec = NS(start=4, end=8, surface='一が動く', reading='いつがうごく', strokes=keys, shifts=())
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.editor = self.w
        self.a._quick_text = None
        self.a._reinput = make_reinput([rec])
        self.a._reconversion_transform = lambda widget, keysym: False
        self.a._forget_bracket_cycle = lambda: None
        self.a._after_ime_char_insert = lambda widget: None
        self.a._pick_mode = None
        for p in (mock.patch.object(ime_watch, 'composition_active', lambda hwnd: False),
                  mock.patch.object(app, 'ime_confirmed_char_event', lambda event: None)):
            p.start()
            self.addCleanup(p.stop)

    def press(self, keysym, first, last):
        self.w.tag_add('sel', first, last)
        app.CorrectNoteApp._on_selection_transform(self.a, NS(widget=self.w, keysym=keysym, char='', state=0))
        return self.w.get('1.0', 'end-1c')

    def test_f6_uses_the_typed_keys(self):
        self.assertEqual(self.press('F6', '1.4', '1.8'), '前の字 いちがうごく')     # IME の読み（いつ）ではない

    def test_f7_too(self):
        self.assertEqual(self.press('F7', '1.4', '1.8'), '前の字 イチガウゴク')

    def test_not_typed_keeps_the_old_way(self):
        # 打った確定に入っていない字を含む範囲は、今までどおり（形態素の読み）
        self.assertIsNone(self.a._typed_selection_reading(self.w, '1.0', '前の字 一'))

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_F6_FROM_KEYS': '0'}):
            self.assertIsNone(self.a._typed_selection_reading(self.w, '1.4', '一が動く'))
        self.assertEqual(self.a._typed_selection_reading(self.w, '1.4', '一が動く'), 'いちがうごく')


if __name__ == '__main__':
    unittest.main()
