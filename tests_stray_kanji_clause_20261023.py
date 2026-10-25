"""1打の打ち違いを IME が漢字の語にした跡（紛れ込んだ漢字）に紫を付ける（2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class StrayKanjiClauseTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def purple(self, res):
        return [tuple(x[:2]) for x in res['odd_spans']]

    def test_surname_that_pairs_back_to_a_common_noun(self):
        # ともだち の だ を ぶ と打った ともぶち を、IME が地名 友淵 にした。友達を待つ は語の組の表に在る
        line = '公園で友淵を待った。'
        res = self.run_ime(line, [('友淵', 'ともぶち'), ('友淵を', 'ともぶちを')])
        self.assertEqual(res['corrected'], line)
        self.assertIn((3, 5), self.purple(res))

    def test_extra_key_after_a_finished_sentence(self):
        # ました の後ろに隣のキー て を1打巻き込み、IME が 手 にした
        line = 'ケーキを作りました手'
        res = self.run_ime(line, [('手', 'て')])
        self.assertEqual(res['corrected'], line)
        self.assertIn((9, 10), self.purple(res))

    def test_line_ending_in_object_without_verb(self):
        # まつ の ま を隣の な と打った なつ を、IME が 夏 にした（を で終わり、述語が無い）
        line = 'バス停で先生を夏'
        res = self.run_ime(line, [('夏', 'なつ')])
        self.assertEqual(res['corrected'], line)
        self.assertIn((7, 8), self.purple(res))

    def test_correct_lines_stay_clean(self):
        # 名前・接尾の付いた語・述語の後ろの名詞・数を言う行には紫を付けない
        for line, pairs in (('駅で田中を待った。', [('田中', 'たなか'), ('田中を', 'たなかを')]),
                            ('佐藤さんに手紙を書いた。', [('佐藤', 'さとう')]),
                            ('これは写真家です。', [('写真家', 'しゃしんか')]),
                            ('昨日読んだ本', [('本', 'ほん')]),
                            ('牛乳を二本', [('二本', 'にほん')]),
                            ('新しい靴を買った。', [('新しい', 'あたらしい'), ('靴を', 'くつを')])):
            res = self.run_ime(line, pairs)
            self.assertEqual(res['corrected'], line)
            self.assertEqual(res['odd_spans'], [], line)


if __name__ == '__main__':
    unittest.main()
