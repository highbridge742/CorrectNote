# -*- coding: utf-8 -*-
"""F5 予測のカスタム候補は、出す時の IME の形で選ぶ（うに 11-21 16:52Z 仕様変更「予測カスタムは、IMEが全角モードの時は
全角用のものを出し、半角モードの時は半角のものを出すようにする。カスタム編集は、上のボタンを「全角時」「半角時」という名称に
変える」）。CN_PREDICT_CUSTOM_BY_IME（=0 で前の形: タブの字に全角があるかで選ぶ）。IME の形は作り物（試験の机の IME に依らない）。"""
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import f5_predict as F
import ime_watch


class ByIme(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        F.set_provider(None)
        p = mock.patch.dict(os.environ, {'CN_F5_CLIP_NOUNS': '0', 'CN_PREDICT_CUSTOM_BY_IME': '1'})
        p.start()
        self.addCleanup(p.stop)

    def at(self, text, wide_ime):
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', text)
        self.w.mark_set('insert', 'end-1c')
        before = self.w.get('insert linestart', 'insert')
        app = NS(settings={})
        with mock.patch.object(ime_watch, 'wide_input', lambda hwnd: wide_ime), \
                mock.patch.object(F, 'ime_predictions', lambda *a, **k: None):
            return F.candidates(app, self.w, 1, len(before), before)

    def test_sentence_end_list_follows_the_ime(self):
        # 英字だけの行でも、IME が全角の形なら全角の一覧・日本語の行でも、IME が半角なら半角の一覧
        self.assertEqual(self.at('I read the book', True), F.default_list('end_wide'))
        self.assertEqual(self.at('今日は本を読みます', False)[:3], F.default_list('end_narrow')[:3])

    def test_line_head_list_follows_the_ime(self):
        self.assertEqual(self.at('line one' + chr(10), True)[:3], F.default_list('head_wide')[:3])
        self.assertEqual(self.at('今日の会議' + chr(10), False)[:3], F.default_list('head_narrow')[:3])

    def test_unknown_ime_falls_back_to_the_text(self):
        self.assertEqual(self.at('I read the book', None), F.default_list('end_narrow'))     # 前の選び方（タブの字）
        self.assertEqual(self.at('今日は本を読みます', None)[:3], F.default_list('end_wide')[:3])

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_CUSTOM_BY_IME': '0'}):
            self.assertEqual(self.at('I read the book', True), F.default_list('end_narrow'))
            self.assertEqual(F.list_label('end_wide'), '文末（全角あり）')

    def test_window_button_names(self):
        self.assertEqual([F.list_label(n) for n in ('end_wide', 'end_narrow', 'head_wide', 'head_narrow')],
                         ['全角時', '半角時', '全角時', '半角時'])
        import ui_lang_en
        self.assertEqual(ui_lang_en.TABLE.get('全角時'), 'Full-width input')
        self.assertEqual(ui_lang_en.TABLE.get('半角時'), 'Half-width input')


@unittest.skipUnless(sys.platform == 'win32', 'Windows だけ')
class WideInput(unittest.TestCase):
    """IME の形を読むだけ（開いている・変換の形）。IME を切り替えない。"""

    def fake_imm(self, opened, conv):
        def get_conv(himc, pconv, psent):
            pconv._obj.value = conv
            return 1
        return NS(ImmGetContext=lambda h: 5, ImmReleaseContext=lambda h, c: 1, ImmGetOpenStatus=lambda c: opened,
                  ImmGetConversionStatus=get_conv)

    def test_modes(self):
        for opened, conv, want in ((False, 0x9, False), (True, 0x0, False), (True, 0x1, True), (True, 0x8, True),
                                   (True, 0x9, True)):
            with mock.patch.object(ime_watch, '_imm32', lambda o=opened, c=conv: self.fake_imm(o, c)), \
                    mock.patch.object(ime_watch, 'HAS_SUPPORT', True):
                self.assertEqual(ime_watch.wide_input(1), want, (opened, conv))
        self.assertIsNone(ime_watch.wide_input(0))


if __name__ == '__main__':
    unittest.main()
