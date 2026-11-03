# -*- coding: utf-8 -*-
"""語の組の表の「の」「連体」の行（名詞＋の＋名詞・形容詞＋名詞・2026-10-30）の試験。"""
import unittest

import collocation_repair as R


class NounPartnerTests(unittest.TestCase):
    def test_same_reading_noun_after_no_is_fixed(self):
        marks = R.find('添付の史料', 'kana')
        self.assertEqual([(m[0], m[1], m[2], m[3]) for m in marks], [(3, 5, '資料', True)])

    def test_familiar_noun_after_adjective_is_only_marked(self):
        saved = R._familiar
        R._familiar = lambda w: w == '変心' or saved(w)
        try:
            marks = R.find('早い変心をお願いします', 'kana')
        finally:
            R._familiar = saved
        self.assertTrue(marks)
        self.assertTrue(all(m[2] is None for m in marks))

    def test_correct_pairs_are_kept(self):
        for line in ('会議の資料を配る', '出張の精算を済ませた', '新しい会社に就職した。', '新しい歌詞を覚えた。',
                     '打ち合わせの議事録を共有しました。', '新しい住宅が建った'):
            for method in ('kana', 'romaji'):
                self.assertEqual(R.find(line, method), [], (line, method))

    def test_noun_before_its_follower_is_marked(self):
        marks = R.find('しっかり撹乱しておきます。', 'kana')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(4, 6, None)])

    def test_familiar_same_reading_before_negai_is_fixed(self):
        # 〜願います の前は頼む事柄。身近な語（ここでは仮に 傘下 を身近な語とする）でも、同じ読みの表の語が1つなら直す
        saved = R._familiar
        R._familiar = lambda w: w == '傘下' or saved(w)
        try:
            marks = R.find('傘下願います', 'romaji')
        finally:
            R._familiar = saved
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(0, 2, '参加')])

    def test_split_noun_run_before_follower_is_joined(self):
        marks = R.find('明日は層談します', 'romaji')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(3, 5, '相談')])

    def test_noun_runs_that_are_compounds_are_kept(self):
        for line in ('資料作成します', '日程調整します', '書類提出いたします', 'よろしくお願いいたします'):
            for method in ('kana', 'romaji'):
                self.assertEqual(R.find(line, method), [], (line, method))

    def test_correct_followers_are_kept(self):
        for line in ('了解しました', '受領しました', '幸いです', '説明します', '返信します'):
            for method in ('kana', 'romaji'):
                self.assertEqual(R.find(line, method), [], (line, method))

    def test_two_table_nouns_split_at_to_are_joined(self):
        # 表の2語（ノート・表）の読みが、IME で 〜と＋〜 に切れた形
        marks = R.find('ノーとヒョウを送ります', 'kana')
        self.assertEqual([(m[0], m[1], m[2], m[3]) for m in marks], [(0, 6, 'ノート表', True)])
        for line in ('ポストと表を送ります', 'データと表を作ります', 'カードと手紙を送ります'):
            self.assertEqual(R.find(line, 'kana'), [], line)

    def test_upper_row_slip_before_desu_is_only_marked(self):
        # ローマ字で上下のキー（s と w）の打ち違い。上下は紫だけ
        marks = R.find('再々です', 'romaji')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(0, 2, '幸い')])
        for line in ('ワクワクです', 'ゆっくりです', '幸いです'):
            for method in ('kana', 'romaji'):
                self.assertEqual(R.find(line, method), [], (line, method))

    def test_one_kana_apart_rare_noun_is_only_marked(self):
        # かな1字だけ違う読み（離れたキー）: めったに使わない語のときだけ紫
        # 候補が1つで直し先が身近な語なら直す
        marks = R.find('早産いたします', 'romaji')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(0, 2, '相談')])
        # かな入力では ざ／だ は隣のキーでも抜けでもないので候補にしない（うに 10-30）
        self.assertEqual(R.find('早産いたします', 'kana'), [])
        for line in ('研究いたします', '新しい住宅', '承知いたしました'):
            for method in ('kana', 'romaji'):
                self.assertEqual(R.find(line, method), [], (line, method))

    def test_desu_swallowed_by_line_end_katakana_is_only_marked(self):
        # 行末の カタカナの語が読みの終わりに です を抱え、左の名詞にも同じ読みの身近な語がある形（ここでは仮に
        # メルセデス を珍しい語とする）
        saved = R._rare
        R._rare = lambda w: w == 'メルセデス' or saved(w)
        try:
            marks = R.find('汽車メルセデス。', 'kana')
            kept = [R.find(line, 'kana') for line in ('機械メルセデス', '汽車メルセデスが来た')]
        finally:
            R._rare = saved
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(2, 7, None)])
        self.assertEqual(kept, [[], []])

    def test_rare_name_right_after_te_at_line_end_is_only_marked(self):
        marks = R.find('走ってトウキョウ', 'kana')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(3, 8, None)])
        for line in ('夏休みに旅行してハワイ。', '家に帰って東京', 'いつもお世話になっております'):
            self.assertEqual(R.find(line, 'kana'), [], line)

    def test_quoting_tte_is_not_treated_as_dropped_keys(self):
        for line in ('オセアニアって知ってる？', 'いつもお世話になっております'):
            self.assertEqual(R.find(line, 'romaji'), [], line)


    def test_noun_before_onegai_with_vertical_key_is_fixed_in_romaji(self):
        # 作った例: ほうこく の h を上の y にした読み（ようこく）の珍しい語＋お願いします
        marks = R.find('陽刻お願いします', 'romaji')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(0, 2, '報告')])


    def test_small_vowel_head_from_romaji_order_slip_is_fixed(self):
        # 作った例: shimasita を shimatsia と打った形（しまつぃあ）
        marks = R.find('連絡しまつぃあ。', 'romaji')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(4, 7, 'した')])
        self.assertEqual(R.find('連絡しまつぃあ。', 'kana'), [])
        self.assertEqual(R.find('パーティーに行った。', 'romaji'), [])


    def test_te_then_rare_name_with_matching_head_is_fixed(self):
        # 作った例: 〜て のあと います の頭（いま）まで打って、予測変換で別の固有名詞を選んだ形
        marks = R.find('資料を送ってイマジン。', 'romaji')
        self.assertEqual([(m[0], m[1], m[2]) for m in marks], [(6, 10, 'います')])


    def test_hepburn_distance_counts_keystrokes(self):
        # 作った例: n の抜けは1打、し／じ は shi／ji で2打
        self.assertEqual(R._hepburn_distance('かんたん', 'かんた'), 1)
        self.assertEqual(R._hepburn_distance('さし', 'さじ'), 2)

    def test_kana_far_substitution_is_not_a_candidate(self):
        # 作った例: ようこく／ほうこく は かなでは よ と ほ のキーが隣でも抜けでもない。ローマ字では1打違いなので直す
        self.assertEqual(R.find('陽刻お願いします', 'kana'), [])
        self.assertEqual([m[2] for m in R.find('陽刻お願いします', 'romaji')], ['報告'])

    def test_row_rank_follows_table_order(self):
        # 表の行で先に書いた語ほど前（並んだときの決め手）
        rank = R._row_rank('続', 'お願い')
        self.assertLess(rank['返信'], rank['記入'])


if __name__ == '__main__':
    unittest.main()
