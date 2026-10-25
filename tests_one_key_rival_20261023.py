"""確定した文節の1打の戻しで、かなの語・助詞＋語の読みも競わせる（補正C・2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class OneKeyRivalTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_kana_word_is_counted(self):
        # これ に き を巻き込んだ こきれ。漢字の語（見切れ）だけを数えて決めない
        got = self.run_ime('濃きれから出かけます。', [('濃きれ', 'こきれ')])
        self.assertNotIn('みきれ', got)
        self.assertNotIn('見切れ', got)

    def test_particle_plus_word_is_counted(self):
        # は を す と打った すはやく。は を落とした 早く に決めない
        got = self.run_ime('明日素速く起きる。', [('素速く', 'すはやく')])
        self.assertNotEqual(got, '明日早く起きる。')

    def run_marks(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_undecided_slip_is_marked(self):
        # 決めずに触らないときも、その文節に印を残す（迷うなら紫）
        r = self.run_marks('明日素速く起きる。', [('素速く', 'すはやく')])
        if r['corrected'] == '明日素速く起きる。':
            self.assertTrue(any(a <= 2 and 5 <= b for a, b in r['unsure_spans']), r['unsure_spans'])

    def test_faithful_clause_is_not_marked(self):
        # 打ったとおりに読める文節（語＋助詞）には印を付けない
        r = self.run_marks('明日は課題を出す。', [('課題を', 'かだいを'), ('明日は', 'あしたは')])
        self.assertEqual(r['unsure_spans'], [])


if __name__ == '__main__':
    unittest.main()
