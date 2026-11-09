# -*- coding: utf-8 -*-
"""kana_piece_word（かなの切れ端を語に戻す段）と、前の行とつなぐ判定の小書きのかな（2026-11-08 手分けA）。例は作った文。"""
import os
import unittest

import kana_piece_word as K


class SuffixPiece(unittest.TestCase):
    def test_purple_piece_after_noun(self):
        # 名詞＋紫のかな: 漢字を付けた組が辞書に1語として在るものが1つだけ
        self.assertEqual(K.propose('駐車けん', [(2, 4)]), [(2, 4, '券')])
        self.assertEqual(K.propose('整理けんが無い', [(2, 4)]), [(2, 4, '券')])
        self.assertEqual(K.propose('経済けん', [(2, 4)]), [(2, 4, '圏')])

    def test_placed_noun_in_kana_line(self):
        # かなの行で前の段が漢字に置いた名詞のすぐ後ろに残ったかな
        out = K.repair_line('ちゅうしゃけん', {'corrected': '駐車けん', 'odd_spans': []})
        self.assertEqual(out['corrected'], '駐車券')
        out = K.repair_line('かいぎしつ', {'corrected': '会議しつ', 'odd_spans': []})
        self.assertEqual(out['corrected'], '会議室')

    def test_no_purple_no_change(self):
        self.assertEqual(K.propose('駐車けん', []), [])

    def test_verb_after_placed_noun_untouched(self):
        out = K.repair_line('しょくじした', {'corrected': '食事した', 'odd_spans': []})
        self.assertEqual(out['corrected'], '食事した')


class ShortKanaRun(unittest.TestCase):
    def test_voiced_mark_neighbour(self):
        # かな入力で ゛ の隣のキー（せ）を押した: たふ＋せ → たぶ
        self.assertEqual(K.propose('たふせ'), [(0, 3, 'タブ')])
        self.assertEqual(K.propose('たふせ。'), [(0, 3, 'タブ')])

    def test_correct_short_kana_untouched(self):
        for s in ('かもね', 'はい', 'そうだね', 'ありがとう', 'またね', 'おはよう', 'えっと', 'まあね', 'なるほど', 'いいね'):
            self.assertEqual(K.propose(s), [], s)

    def test_switch(self):
        os.environ['CN_KANA_PIECE_WORD'] = '0'
        try:
            self.assertEqual(K.propose('たふせ'), [])
            self.assertEqual(K.propose('駐車けん', [(2, 4)]), [])
        finally:
            del os.environ['CN_KANA_PIECE_WORD']


class JoinSmallKana(unittest.TestCase):
    def test_head_cut_before_small_kana_is_not_particle(self):
        import correction_entry as CE
        # に｜ゅ力 の に は助詞ではない（語の切れ端）: 前の行とつながない
        self.assertEqual(CE._continuation_prefix('・メモ', 'にゅ力ミス'), '')
        # 本当の助詞で始まる行は今まで通りつなぐ
        self.assertNotEqual(CE._continuation_prefix('会議の資料を送ったので', 'にもつが届いたら確認して'), None)


if __name__ == '__main__':
    unittest.main()
