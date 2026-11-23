# -*- coding: utf-8 -*-
"""再入力変換で、打った半角の英数を全角にしない（2026-11-23 うにさん「半角アルファベットを再入力変換すると、全角にされた。
変えない」）。開いた範囲に半角の英数があり全角の英数が無い時は、書く字の全角の英数・記号を半角へ戻す。かなと混ざった範囲
でも英数の所だけ。全角で打ってあった範囲・かなだけの範囲は今までどおり。CN_REINPUT_KEEP_ASCII=0 で前の形。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app


class KeepAscii(unittest.TestCase):
    def test_rule(self):
        f = app._keep_typed_ascii
        self.assertEqual(f('abc', 'ａｂｃ'), 'abc')
        self.assertEqual(f('abc', 'ＡＢＣ'), 'ABC')
        self.assertEqual(f('tv', 'ｔｖ'), 'tv')
        self.assertEqual(f('でーたa', 'データａ'), 'データa')               # かなと混ざった範囲は英数の所だけ
        self.assertEqual(f('v2', 'ｖ２'), 'v2')
        self.assertEqual(f('ａｂｃ', 'ａｂｃ'), 'ａｂｃ')                   # 全角で打ってあった範囲は今までどおり
        self.assertEqual(f('かいぎ', '会議'), '会議')                       # かなだけの範囲は今までどおり
        self.assertEqual(f('かいぎ', 'ＫＡＩＧＩ'), 'ＫＡＩＧＩ')
        self.assertEqual(f('abc', 'エービーシー'), 'エービーシー')          # 英数でない候補はそのまま

    def wired(self, environ):
        written = []
        inst = NS(state=dict(original='abc'), widget=None)
        inst._open_span = lambda *a: True
        inst._write = lambda text, keep_cursor=False: written.append(text)
        inst.settle = lambda *a: None
        inst._drop = lambda *a: None
        a = object.__new__(app.CorrectNoteApp)
        with mock.patch.dict(os.environ, dict(environ, CN_REINPUT_BIG_FONT='0', CN_REINPUT_CARET_FLASH='0')):
            a._wire_reinput_view(inst)
            inst._write('ａｂｃ')
            inst._write('ａｂｃ', True)
        return written

    def test_the_write_of_reinput_keeps_ascii(self):
        self.assertEqual(self.wired({}), ['abc', 'abc'])

    def test_switch_back(self):
        self.assertEqual(self.wired({'CN_REINPUT_KEEP_ASCII': '0'}), ['ａｂｃ', 'ａｂｃ'])   # 前の形: 全角のまま書く


if __name__ == '__main__':
    unittest.main()
