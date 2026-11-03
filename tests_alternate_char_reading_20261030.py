# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""解析が読めた一字の漢字の別の音訓（目＝ぼく）は、同じ読みの別の字の根拠にだけ使い、
打ち違いの戻し（を を抜く）とは重ねない（補正担当・2026-10-30。正しい文の を目 が 僕 になっていた）。例文は作ったもの。"""
import unittest

import app as C
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class AlternateCharacterReadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def test_key_repair_is_not_stacked_on_an_alternate_single_kanji_reading(self):
        for line in ('旅行についてを目につく所に書く', '料金についてを目に付く場所へ'):
            res = C.correct_line(line, self.store, input_method='kana', dict_index=self.index)
            self.assertNotIn('僕', res['corrected'], line)
            self.assertIn('目', res['corrected'], line)

    def test_common_katakana_word_is_kept(self):
        # 片仮名だけのよく使う語は、周りの読みが異様でも打ち違いの戻しの的にしない（作った例）
        import contextual_repair as CR
        self.assertTrue(CR._common_katakana_word('メニュー'))
        self.assertFalse(CR._common_katakana_word('メなュー'))
        self.assertFalse(CR._common_katakana_word('ギ'))

    def test_colloquial_suru_tail_is_not_a_repair(self):
        # 作った例: 直した語（遺伝）の後ろの しょう を する の意志形の崩れと読んで成り立たせない
        for line in ('ゆがいぶんしょう', 'もがいぶんしょう'):
            res = C.correct_line(line, self.store, input_method='kana', dict_index=self.index)
            self.assertNotIn('遺伝', res['corrected'], line)


if __name__ == '__main__':
    unittest.main()
