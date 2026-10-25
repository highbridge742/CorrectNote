"""送り仮名・付属語のかなを IME が同じ読みの漢字にした形を、かなに戻す（2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class AbsorbedKanaTests(unittest.TestCase):
    def run_ime(self, face, pairs=()):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_past_tense_kana_made_kanji(self):
        # たべた の た を IME が 田 にした
        self.assertEqual(self.run_ime('昨日はカレーを食べ田。', [('食べ田', 'たべた')])['corrected'], '昨日はカレーを食べた。')
        self.assertEqual(self.run_ime('本を読ん打。', [('読ん打', 'よんだ')])['corrected'], '本を読んだ。')

    def test_masu_kana_made_kanji(self):
        # しました の しま を IME が 島 にした
        self.assertEqual(self.run_ime('先生に連絡島した。', [('連絡島した', 'れんらくしました')])['corrected'],
                         '先生に連絡しました。')

    def test_real_compounds_stay(self):
        # 用言＋漢字の語として在る組（書き手・飲み屋・勉強家）は触らない
        for line in ('書き手が足りない。', '飲み屋に行く。', '兄は勉強家だ。', '寒い日だった。'):
            res = self.run_ime(line)
            self.assertEqual(res['corrected'], line)
            self.assertEqual(res['odd_spans'], [], line)


if __name__ == '__main__':
    unittest.main()
