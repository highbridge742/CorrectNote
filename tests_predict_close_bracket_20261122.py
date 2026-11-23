# -*- coding: utf-8 -*-
"""予測の一覧の先頭に、開いたままの括弧の閉じ（2026-11-21 17:16Z うにさん「文の途中でも文末でも、カーソルの右に文字がない時は
閉じる括弧の候補を出す。これは前の行から続くものでも候補に出す…下の行で閉じている可能性もある。それも気を付ける」）。
CN_PREDICT_CLOSE_BRACKET=0 で前の形。作った例文だけ（IME の予測は作り物）。"""
import os
import time
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import f5_predict as F
import ime_watch


class CloseBracket(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        F.set_provider(None)
        for p in (mock.patch.dict(os.environ, {'CN_F5_CLIP_NOUNS': '0'}),
                  mock.patch.object(ime_watch, 'wide_input', lambda hwnd: None),
                  mock.patch.object(F, 'ime_predictions', lambda *a, **k: ['予測']),
                  mock.patch.object(F, 'next_chars', lambda *a, **k: [])):
            p.start()
            self.addCleanup(p.stop)

    def at(self, text, index):
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', text)
        self.w.mark_set('insert', index)
        before = self.w.get('insert linestart', 'insert')
        app = NS(settings={})
        got = F.candidates(app, self.w, int(self.w.index('insert').split('.')[0]), len(before), before)
        return got, app

    def test_mid_sentence_and_sentence_end(self):
        got, app = self.at('彼は「そうで', '1.end')
        self.assertEqual(got[0], '」')                                        # 文の途中でも先頭に
        self.assertIn('予測', got)
        self.assertEqual(app._f5_close_items, ['」'])                         # 記号だけでも落とさない印
        got, _ = self.at('彼は「本当に『そうです', '1.end')
        self.assertEqual(got[:2], ['』', '」'])                               # 内側から

    def test_opened_on_a_line_above(self):
        got, _ = self.at('彼は「今日の\n予定は', '2.end')
        self.assertEqual(got[0], '」')                                        # 上の行から続く
        got, _ = self.at('「今日の\n\n予定は', '3.end')
        self.assertNotIn('」', got)                                           # 空の行より上は見ない

    def test_closed_below_is_left_out(self):
        got, _ = self.at('彼は「今日の\n予定は\n終わり」です', '2.end')
        self.assertNotIn('」', got)                                           # 下の行で閉じている
        got, _ = self.at('（「a\nb\n」c', '2.end')
        self.assertEqual(got[0], '）')                                        # 内側は下で閉じ、外側は開いたまま

    def test_not_at_line_head(self):
        # 17:31Z うにさん「閉じ括弧は、行頭の予測には出さない」: 行頭・行頭の空白や記号だけの時は出さない
        got, _ = self.at('彼は「今日の\n', '2.0')
        self.assertNotIn('」', got)
        got, _ = self.at('彼は「今日の\n　・', '2.end')
        self.assertNotIn('」', got)
        got, _ = self.at('彼は「今日の\n予定', '2.end')
        self.assertEqual(got[0], '」')                                        # 字があれば出す

    def test_not_when_text_is_on_the_right(self):
        got, _ = self.at('彼は「そうで', '1.3')
        self.assertNotIn('」', got)

    def test_half_width_and_edges(self):
        got, _ = self.at('call(a, [b', '1.end')
        self.assertEqual(got[:2], [']', ')'])
        got, _ = self.at('', '1.0')                                           # 空のタブ
        self.assertNotIn('」', got)
        got, _ = self.at('「最後の行', 'end-1c')                               # 最後の行・1行目
        self.assertEqual(got[0], '」')

    def test_more_pairs_20261122(self):
        # 01:43Z・01:44Z うにさん「これの閉じる括弧に対応する」: < ≪ ‘ 〝（〟・〞 で閉じる）と "（数で見る）。
        # 01:50Z 訂正「`'この2つが対になります」: ` は開き・' は閉じ（' は it's などにも出るので開きに数えない）
        for text, want in (('<div class', '>'), ('≪見出し', '≫'), ('‘引用', '’'), ('〝強調', '〟'),
                           ('"quoted', '"'), ('`code', "'")):
            got, _ = self.at('彼は' + text, '1.end')
            self.assertEqual(got[0], want, (text, got))
        for text in ('a < b ok', 'x<3 です', '〝強調〞後', '"a" b'):
            got, _ = self.at('彼は' + text, '1.end')
            self.assertFalse(set(got) & set('>〟"`'), (text, got))             # 比べる < ・閉じたもの・偶数は出さない
        got, _ = self.at("it's fine", '1.end')
        self.assertNotIn("'", got)                                            # ' は開きに数えない（it's）
        got, _ = self.at("`a\nb\nc' d", '2.end')
        self.assertNotIn("'", got)                                            # カーソルより後に ' があれば閉じている
        got, _ = self.at('〝上\n続き', '2.end')
        self.assertEqual(got[0], '〟')                                         # 上の行から続く
        got, _ = self.at('"上\n続き\n下"で', '2.end')
        self.assertNotIn('"', got)                                            # 下に対の字がある

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_CLOSE_BRACKET': '0'}):
            got, _ = self.at('彼は「そうで', '1.end')
            self.assertNotIn('」', got)                                       # 前の形: 文の途中では出さない

    def test_bounded_scan_is_quick(self):
        text = '\n'.join('「長い行' + 'あ' * 200 for _ in range(5000))
        self.w.delete('1.0', 'end'); self.w.insert('1.0', text); self.w.mark_set('insert', '2500.end')
        t = time.perf_counter()
        for _ in range(10):
            F.close_brackets(self.w, self.w.get('insert linestart', 'insert'))
        self.assertLess((time.perf_counter() - t) / 10, 0.05)                 # 上下 40 行まで（主スレッドで長く回らない）


if __name__ == '__main__':
    unittest.main()
