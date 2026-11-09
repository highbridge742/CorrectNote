# -*- coding: utf-8 -*-
"""割れた身近な語を1打の戻しで1語にまとめる候補（2026-11-09 手分けA）。例は作った読み。"""
import os
import unittest

import split_merge as S


class SplitMerge(unittest.TestCase):
    def test_kana_keeps_dakuten(self):
        v = S.variants('かで', 'kana')
        self.assertIn('かだ', v)          # て の隣の た に ゛ を保つ
        self.assertNotIn('かて', v)       # ゛ を落とすことはしない（゛ は1つのキー）

    def test_romaji_letters(self):
        # ローマ字入力では ゛ のキーという見方をしない（字ごとの1打違い: corrector.adjacent_slip の romaji）
        self.assertEqual(S.variants('かで', 'romaji'), {x for x in S.variants('かで', 'romaji')})
        self.assertNotEqual(S.variants('かで', 'romaji'), S.variants('かで', 'kana'))

    def test_faces_compound(self):
        self.assertIn('巨大化', S.faces('きょだいか'))

    def test_switch(self):
        os.environ['CN_SPLIT_MERGE'] = '0'
        try:
            self.assertFalse(S.on())
        finally:
            del os.environ['CN_SPLIT_MERGE']


if __name__ == '__main__':
    unittest.main()
