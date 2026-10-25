"""ローマ字の隣り合う2打の入れ替わり（英字が残らない形）を紫の範囲の中で戻す（romaji_swap_repair・2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line
from romaji_swap_repair import swap_readings


class RomajiSwapRepairTests(unittest.TestCase):
    def run_line(self, face, input_method):
        st = initial()
        return correct_line(face, st.store, context_vocab={}, input_method=input_method, dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_swap_readings(self):
        # asa の a と s が入れ替わると saa（さあ）。nakusite の n と a で ankusite（あんくして）
        self.assertIn('あさ', swap_readings('さあ'))
        self.assertIn('なくして', swap_readings('あんくして'))

    def test_romaji_swap_is_fixed(self):
        # saifu → sahiu（f と i の入れ替わりを訓令式の hu で打った形）・yuuhan → yuhuan・jiyuu → jiuyu
        self.assertEqual(self.run_line('さひうを机に置いた。', 'romaji')['corrected'], '財布を机に置いた。')
        self.assertEqual(self.run_line('母がゆふあんを作ってくれた。', 'romaji')['corrected'], '母が夕飯を作ってくれた。')
        self.assertEqual(self.run_line('今日はじうゆに過ごした。', 'romaji')['corrected'], '今日はじゆうに過ごした。')

    def test_other_one_key_slips_are_not_swapped(self):
        # 1打多い・1打抜けの戻しが入れ替わりより良く見える所は、入れ替わりと決めない（さあ は さ＋a の2度押しとも読める）
        r = self.run_line('さあからずっと雨だった。', 'romaji')
        self.assertEqual(r['corrected'], 'さあからずっと雨だった。')
        self.assertTrue(r['odd_spans'])

    def test_kana_input_is_not_touched(self):
        # かな入力では打鍵の入れ替わりの形にならないので、この直しは何もしない
        from romaji_swap_repair import apply
        line = 'さひうを机に置いた。'
        before = dict(corrected=line, odd_spans=[[0, 3]], odd_reasons=[[0, 3, '']])
        st = initial()
        self.assertEqual(apply(line, before, 'kana', st.store, st.dict_index), before)
        self.assertNotEqual(apply(line, before, 'romaji', st.store, st.dict_index)['corrected'], line)

    def test_correct_lines_are_kept(self):
        for line in ('さあ、出かけよう。', 'この道をまっすぐ行くと公園に出ます。', '窓を閉めてカーテンを引いた。'):
            self.assertEqual(self.run_line(line, 'romaji')['corrected'], line)


if __name__ == '__main__':
    unittest.main()
