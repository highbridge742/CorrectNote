"""音と活用の決まりでありえないかなの並びに紫を付ける（2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class ImpossibleKanaTests(unittest.TestCase):
    def run_line(self, line):
        st = initial()
        return correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def purple(self, line):
        res = self.run_line(line)
        self.assertEqual(res['corrected'], line)
        return [line[x[0]:x[1]] for x in res['odd_spans']]

    def test_small_vowel_that_cannot_join(self):
        # いれた の い を Shift で小書きにした（語の頭の小書き）
        self.assertIn('ぃ', self.purple('自転車のタイヤに空気をぃれた'))

    def test_voiced_after_small_tsu(self):
        # った の た に濁点を付けすぎた
        self.assertIn('っだ', self.purple('映画を見に行くことになっだ'))

    def test_large_tsu_where_sokuon_belongs(self):
        # 走っている の っ を小書きにし忘れた
        self.assertIn('走つ', self.purple('公園で子供が走つている'))

    def test_doubled_kana_after_predicate(self):
        # いる の る を2度押した
        self.assertIn('るる', self.purple('毎晩日記を書いているる'))

    def test_correct_lines_stay_clean(self):
        for line in ('かつては賑やかな町だった。', '目標を立てて毎日続ける。', 'かわいぃ犬がいた。', 'ほんをよんでくださぃ。',
                     'フィルムカメラを買った。', 'ティッシュを取ってください。', '母はいつもここに座る。',
                     'ぐっずを買った。', 'ぴっづぁを食べた。'):
            res = self.run_line(line)
            self.assertEqual(res['odd_spans'], [], line)


if __name__ == '__main__':
    unittest.main()
