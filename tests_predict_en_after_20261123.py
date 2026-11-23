# -*- coding: utf-8 -*-
"""英文の後の予測（2026-11-23 説明書担当の見つけ・うにさん承認）。英文のタブで「.」「!」「?」の後や、英文の行の次の行頭で
予測を出すと、日本語の接続詞（しかし・そして…）や日本語の名詞が並んでいた。
・前の文（同じ行の前の文・行頭なら上の行の最後の文）がラテン文字の英文なら、カスタムの半角時の一覧（無ければ既定）と、
  近くの行の英単語の名詞だけを出す（IME が全角の形でも）
・日本語の文の後は今までと同じ。混ざった行は、カーソルの前の文で決める
CN_PREDICT_EN_AFTER=0 で前の形。自分の Text の窓だけ・作った例文。"""
import os
import re
import unittest
from unittest import mock

NARROW = ['#', '*', '>', '+', '-']
_JA = re.compile(r'[぀-ヿ㐀-鿿！-～　-〿]')


class EnglishAfter(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        import ime_watch
        import f5_predict
        # 日本語の文の後に接続詞が出ることを目印に見ているので、接続詞を出す前の形で見る（2026-11-23 うにさん「接続詞の
        # 候補は無しにする」から既定では出さない・tests_predict_no_conj_20261123）
        p0 = mock.patch.dict(os.environ, {'CN_PREDICT_NO_CONJUNCTIONS': '0'})
        p0.start()
        self.addCleanup(p0.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        f5_predict.set_provider(None)
        self.F = f5_predict
        p = mock.patch.object(ime_watch, 'wide_input', lambda hwnd: True)      # IME は全角の形（日本語の入力）
        p.start()
        self.addCleanup(p.stop)

    def at_end(self, text):
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', text)
        self.w.mark_set('insert', 'end-1c')
        before = self.w.get('insert linestart', 'insert')
        row = int(self.w.index('insert').split('.')[0])
        return self.F.candidates(None, self.w, row, len(before), before)

    def english_only(self, got):
        self.assertEqual(got[:len(NARROW)], NARROW, got)
        self.assertFalse([c for c in got if _JA.search(c)], got)                  # 日本語の候補が無い
        for c in got[len(NARROW):]:
            self.assertTrue(c.isascii(), got)                                     # 足すのは英単語の名詞だけ

    def test_after_english_sentence_end(self):
        for text in ('I read the book.', 'Is it ok?', 'Wow, that is great!', 'Meeting notes for the project. We met.'):
            self.english_only(self.at_end(text))

    def test_line_head_after_an_english_line(self):
        # 行頭の印の一覧は IME の形で選ぶまま（2026-11-21 の指定・ここでは全角の形）。上の行が英文なら日本語の名詞を足さない
        heads = self.F.default_list('head_wide')
        for text in ('会議の資料を確認します。\nThis is a pen.\n', '会議の資料を確認します。\nThis is a pen.\n\n'):
            got = self.at_end(text)
            self.assertEqual(got[:len(heads)], heads, got)
            self.assertFalse([c for c in got[len(heads):] if _JA.search(c)], got)   # 「会議」「資料」を足さない
        got = self.at_end('This is a pen.\n会議の資料を確認します。\n')            # 上の行が日本語なら今までどおり
        self.assertTrue({'会議', '資料'} & set(got), got)

    def test_nearby_english_nouns_are_added(self):
        got = self.at_end('The budget report is ready.\nPlease check the budget report.\nThanks.')
        self.english_only(got)
        self.assertTrue({'budget', 'report'} & set(got), got)                     # 近くの行に2回出る英単語

    def test_japanese_sentences_are_unchanged(self):
        got = self.at_end('雨が降ったので、試合は中止になりました。')
        self.assertEqual(got[0], 'だから', got)
        self.assertIn('しかし', self.at_end('本当です!'))                         # 全角の字を含む文は日本語の文
        with mock.patch.dict(os.environ, {'CN_PREDICT_EN_AFTER': '0'}):
            self.assertEqual(self.at_end('雨が降ったので、試合は中止になりました。')[0], 'だから')

    def test_mixed_line_uses_the_sentence_before_the_cursor(self):
        self.english_only(self.at_end('今日は雨です。This is English.'))
        got = self.at_end('This is English. 今日は雨です。')
        self.assertIn('しかし', got)                                              # 前の文は日本語
        got = self.at_end('今日は雨です。\n')                                    # 上の行が日本語の行頭は今までどおり
        self.assertFalse(got[:len(NARROW)] == NARROW, got)

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_EN_AFTER': '0'}):
            got = self.at_end('Wow, that is great!')
        self.assertIn('しかし', got)                                              # 前の形: 英文の後に日本語の接続詞


if __name__ == '__main__':
    unittest.main()
