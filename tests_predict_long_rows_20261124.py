# -*- coding: utf-8 -*-
"""長い行（数万字）で、予測の下ごしらえ・行末の予測が本体を止めない（2026-11-24 公開版 v1.20.0 の検査
tests_gui_encoded_paste で、3万字の行を貼った2回目に本体が 14〜20 秒止まった）。
・近くの行の名詞（_row_nouns・auto_candidates.warm_nouns が行ごとに呼ぶ）は、長い行は頭の ROW_NOUNS_MAX 字だけを形態素に掛ける
  （CN_PREDICT_ROW_NOUNS_CAP=0 で前の形）
・文末らしいか（ends_like_sentence）・IME の予測（ime_predictions）は、カーソルの前の終わりの TOKEN_TAIL 字だけを形態素に掛ける
  （CN_PREDICT_TOKEN_TAIL=0 で前の形）。見るのは最後の語だけなので、答えは短い行と同じ
作った文だけ。"""
import os
import time
import unittest
from unittest import mock

import f5_predict as F

LONG = '長い文章でも全体を保持できます。ABC 😀 ' * 1600


class LongRows(unittest.TestCase):
    def setUp(self):
        F._NOUN_MEMO.clear()

    def test_row_nouns_is_quick_on_a_long_row(self):
        t = time.perf_counter()
        got = F._row_nouns(LONG)
        self.assertLess(time.perf_counter() - t, 1.5)
        self.assertIn('文章', got)                                     # 頭の部分の名詞は数える
        self.assertLessEqual(len(F.row_nouns_head(LONG)), F.ROW_NOUNS_MAX)
        self.assertTrue(F.row_nouns_head(LONG).endswith((' ', '。')))  # 区切りまで（語を途中で切らない）
        short = '会議の資料を確認します。'
        self.assertEqual(F.row_nouns_head(short), short)               # 短い行はそのまま

    def test_tail_gives_the_same_answer(self):
        for tail in ('今日は雨が降りました', '本を読む', '本当ですね', '会議の資料を確認する'):
            long_before = LONG + tail
            self.assertEqual(F.ends_like_sentence(long_before), F.ends_like_sentence(tail), tail)
            self.assertTrue(F.token_tail(long_before).endswith(tail), tail)
            self.assertLessEqual(len(F.token_tail(long_before)), F.TOKEN_TAIL)
        t = time.perf_counter()
        F.ends_like_sentence(LONG + '本を読む')
        self.assertLess(time.perf_counter() - t, 1.0)

    def test_switches(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_ROW_NOUNS_CAP': '0'}):
            self.assertEqual(F.row_nouns_head(LONG), LONG)
        with mock.patch.dict(os.environ, {'CN_PREDICT_TOKEN_TAIL': '0'}):
            self.assertEqual(F.token_tail(LONG), LONG)


if __name__ == '__main__':
    unittest.main()
