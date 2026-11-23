# -*- coding: utf-8 -*-
"""再入力変換で数字＋助数詞の語（「1階に」など）を開いた時、数字はそのまま、助数詞の読みの1字の漢字の同音を候補に足す
（2026-11-23 うにさん「1階と出たものを再変換で1回にしたかったが、選択肢に出なかった」）。IME は1つ目の変換しか返さず、
アプリの候補は助詞を含む読みでは出なかった。字は常用漢字の音訓の表（同梱）から、IME がその読みで読む字に絞る。
CN_REINPUT_COUNTER=0 で前の形。作った例だけ。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app


class Counter(unittest.TestCase):
    def a(self):
        return object.__new__(app.CorrectNoteApp)

    def test_counter_homophones(self):
        got = self.a()._reinput_counter_choices('1階に', '1かいに')
        self.assertEqual(got[0], '1階に', got)                 # 開いた字が先
        self.assertIn('1回に', got)                              # 同音の助数詞
        self.assertTrue(all(c.startswith('1') and c.endswith('に') for c in got), got)   # 数字と助詞はそのまま
        got = self.a()._reinput_counter_choices('3個', '3こ')
        self.assertEqual(got[0], '3個', got)
        self.assertTrue(len(got) > 1, got)

    def test_not_a_counter(self):
        for original, reading in (('会議', 'かいぎ'), ('1階に', 'いっかいに'), ('abc', 'abc'), ('一階に', 'ひとかいに')):
            self.assertEqual(self.a()._reinput_counter_choices(original, reading), [], original)

    def wired(self, environ):
        inst = NS(state=dict(original='1階に'), widget=None)
        inst._open_span = lambda *x: True
        inst._write = lambda *x, **k: None
        inst.settle = lambda *x: None
        inst._drop = lambda *x: None
        inst.choices_for = lambda reading: ['1回に', reading]
        a = self.a()
        with mock.patch.dict(os.environ, dict(environ, CN_REINPUT_BIG_FONT='0', CN_REINPUT_CARET_FLASH='0',
                                               CN_REINPUT_KEEP_ASCII='0')):
            a._wire_reinput_view(inst)
            return inst.choices_for('1かいに')

    def test_reinput_choices_get_them(self):
        got = self.wired({})
        self.assertEqual(got[0], '1回に')                        # IME の1つ目はそのまま先頭
        self.assertEqual(got[-1], '1かいに')                     # 読みそのもの（かな）は最後
        self.assertIn('1階に', got)

    def test_switch_back(self):
        self.assertEqual(self.wired({'CN_REINPUT_COUNTER': '0'}), ['1回に', '1かいに'])


if __name__ == '__main__':
    unittest.main()
