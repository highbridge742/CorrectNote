"""学習で立った語へ、正しい行の助詞を削る・替える戻しをしない（corrector._ime_one_key_respell・2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class LearnedParticleTests(unittest.TestCase):
    def run_learned(self, face, pairs, learned):
        st = initial()
        # 文章から学習と同じく2度見て立てる（janome の無い PC でも同じ形になるよう、語彙に直接入れる）
        for rd, sf in learned:
            st.store.add(rd, sf, '日常会話')
            st.store.add(rd, sf, '日常会話')
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_particle_is_not_cut_to_a_learned_word(self):
        # 学習した 乾き・卵焼き・時期 があっても、川は・卵焼きは・時期は の は は削らない・替えない
        cases = (('遊んだ川は今も流れている。', [('川は', 'かわは')], [('かわき', '乾き')]),
                 ('卵焼きは甘くておいしい。', [('卵焼きは', 'たまごやきは')], [('たまごやき', '卵焼き')]),
                 ('この時期は雨が多い。', [('時期は', 'じきは')], [('じき', '時期')]))
        for face, pairs, learned in cases:
            self.assertEqual(self.run_learned(face, pairs, learned)['corrected'], face)


if __name__ == '__main__':
    unittest.main()
