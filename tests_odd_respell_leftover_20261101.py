# -*- coding: utf-8 -*-
"""紫の所の一部だけを戻して、崩れた変換の残り（1字の漢字・稀な語）が直した字に付いたままの形は決めない（odd_respell・手分けA・2026-11-01）。作った例だけ。"""
import unittest
import odd_respell as O


class LeftoverPieceTests(unittest.TestCase):
    def test_lone_kanji_left_beside_fix(self):
        # 直した字（へ）のすぐ隣に、紫の所に在った珍しい1字の漢字（桶）が残る
        self.assertTrue(O._leftover_piece('机の上桶置く', '机の上へ桶置く', 3, 4))

    def test_common_one_kanji_word_left_is_fine(self):
        # 残った1字の語がよく使う名詞（豆・会）なら、正しく残った語のことが多い
        self.assertFalse(O._leftover_piece('机の上豆置く', '机の上へ豆置く', 3, 4))
        self.assertFalse(O._leftover_piece('秋の音楽会し開く', '秋の音楽会は開く', 2, 6))

    def test_whole_piece_replaced_is_fine(self):
        self.assertFalse(O._leftover_piece('手紙尾書く', '手紙を書く', 2, 3))
        self.assertFalse(O._leftover_piece('窓を開け手ください', '窓を開けてください', 4, 5))

    def test_unchanged_word_outside_purple_not_counted(self):
        # 直した字の隣でも、紫の所の外の語（珈琲）は見ない
        self.assertFalse(O._leftover_piece('毎朝珈琲緒飲む', '毎朝珈琲を飲む', 4, 5))

    def test_plain_form_before_ba_is_bad_join(self):
        # 終止形の動詞のすぐ後ろの ば（仮定の ば は仮定形に付く）は、1打の戻しが語の切れ目をずらした形
        self.assertTrue(O._bad_join('窓を開けて見るば', '窓を開けて来るば'))
        self.assertFalse(O._bad_join('早く来れ場', '早く来れば'))

    def test_particle_pairs_and_plain_verb_adjective(self):
        # 続かない格助詞の並び（がの）・行の終わりの終止形の動詞＋形容詞
        self.assertTrue(O._bad_join('机がな上', '机がの上'))
        self.assertTrue(O._bad_join('水を飲む吉井', '水を飲む早い'))
        self.assertFalse(O._bad_join('京都への旅x', '京都への旅'))
        self.assertFalse(O._bad_join('雨が降る日x', '雨が降る日'))

    def test_stray_mark_turned_into_other_kana(self):
        # 付く先の無い ゛ のキーを別のかなに替えた直しは通らない。前の字を濁れる字に戻す・印を抜く直しは通す
        self.assertTrue(O._mark_replaced('机の上お゛置く', '机の上置け置く'))
        self.assertFalse(O._mark_replaced('机の上ん゛置く', '机の上が置く'))
        self.assertFalse(O._mark_replaced('机の上へ゛置く', '机の上へ置く'))


if __name__ == '__main__':
    unittest.main()
