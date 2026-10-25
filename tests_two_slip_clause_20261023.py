"""1語に打ち違いが2つあって読み直せなかった IME の文節に紫を付ける（2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class TwoSlipClauseTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_noun_with_two_slips_gets_purple(self):
        # ちゃくしゅする の ゃ と ゅ を打ち違えた ちやくしゃする を、IME が 血＋役者 にした
        line = '明日から仕事に血役者する。'
        res = self.run_ime(line, [('血役者する', 'ちやくしゃする')])
        self.assertEqual(res['corrected'], line)
        self.assertIn((7, 10), [tuple(x[:2]) for x in res['odd_spans']])

    def test_verb_with_two_slips_gets_purple(self):
        # たすける を2打打ち違えた たてける を、IME が 縦＋蹴る にした
        line = '困った人を縦蹴る。'
        res = self.run_ime(line, [('縦蹴る', 'たてける')])
        self.assertIn((5, 8), [tuple(x[:2]) for x in res['odd_spans']])

    def test_correct_compounds_stay_clean(self):
        # 正しい複合語（語＋接尾・1字の語＋語・助詞を省いた言い方）には紫を付けない
        for line, pairs in (('これは写真化です。', [('写真化', 'しゃしんか')]),
                            ('これは明確性です。', [('明確性', 'めいかくせい')]),
                            ('今日は車移動する。', [('車移動する', 'くるまいどうする')]),
                            ('昼ご飯食べた。', [('ご飯食べた', 'ごはんたべた')])):
            res = self.run_ime(line, pairs)
            self.assertEqual(res['corrected'], line)
            self.assertEqual(res['odd_spans'], [], line)


if __name__ == '__main__':
    unittest.main()
