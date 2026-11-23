# -*- coding: utf-8 -*-
"""予測に接続詞の一覧（しかし・そして・また…）を出さない（2026-11-23 うにさん「予測候補の、しかし　そして　また　などの
接続詞の候補は無しにする。ニュアンスを予想することはできない」）。文の終わり・読点の後は、接続詞の代わりにクリップボード →
近くの行で多い名詞（見出しの印の後と同じ）。出せる物が無い時は一覧を開かず、左の語の再変換にも行かない（同じ日の
「句点のあとにF5を押すと…句点の前の単語が再変換処理されている」で、はじめの「何も出さず左の語へ」を直した）。
うにさんのカスタムの一覧（行頭・文末）はそのまま。英文の後（CN_PREDICT_EN_AFTER）も今までどおり英語の候補。
CN_PREDICT_NO_CONJUNCTIONS=0 で前の形。自分の Text の窓だけ・作った例文。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import f5_predict as F

CONJ = set(F.CONJ_DEFAULT) | set(F.CONJ_AFTER_COMMA) | {'では', 'それとも', 'なぜなら', 'そのため', 'したがって', 'そこで',
                                                         'ところが', 'それでも', '例えば'}


class NoConjunctions(unittest.TestCase):
    def setUp(self):
        import ime_watch
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        F.set_provider(None)
        p = mock.patch.object(ime_watch, 'wide_input', lambda hwnd: None)
        p.start()
        self.addCleanup(p.stop)

    def at_end(self, text):
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', text)
        self.w.mark_set('insert', 'end-1c')
        before = self.w.get('insert linestart', 'insert')
        row = int(self.w.index('insert').split('.')[0])
        return F.candidates(None, self.w, row, len(before), before)

    def test_no_conjunctions_after_a_sentence_or_comma(self):
        for text in ('雨が降ったので、試合は中止になりました。', '本当ですか？', '本を読み、', 'それは良い！'):
            got = self.at_end(text)
            self.assertFalse(set(got) & CONJ, (text, got))

    def test_clipboard_and_nouns_instead(self):
        with mock.patch.object(F, 'clipboard_text', lambda app: '議事録'):
            got = self.at_end('会議の資料を確認します。' + chr(10) + '会議の予定を連絡します。')
        self.assertEqual(got[0], '議事録', got)
        self.assertIn('会議', got, got)
        self.assertFalse(set(got) & CONJ, got)

    def test_f5_stays_after_a_sentence_end(self):
        self.assertTrue(F.ends_sentence_here('本当です。'))
        self.assertTrue(F.ends_sentence_here('本を読み、'))
        self.assertFalse(F.ends_sentence_here('本を読む'))
        with mock.patch.dict(os.environ, {'CN_PREDICT_NO_CONJUNCTIONS': '0'}):
            self.assertFalse(F.ends_sentence_here('本当です。'))

    def test_english_after_is_unchanged(self):
        got = self.at_end('I read the book.')
        self.assertFalse(set(got) & CONJ, got)
        self.assertTrue(got, got)                                      # 英文の後は英語の候補（半角時の一覧）

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_NO_CONJUNCTIONS': '0'}):
            got = self.at_end('雨が降ったので、試合は中止になりました。')
        self.assertEqual(got[0], 'だから', got)                       # 前の形: 接続詞の一覧


if __name__ == '__main__':
    unittest.main()
