"""かな入力で助詞と隣の字が入れ替わった打ち違いの戻し（2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class ParticleSwapTests(unittest.TestCase):
    def run_ime(self, face, pairs=()):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_wo_after_noun(self):
        res = self.run_ime('姉の結婚式で写真とをった', [('写真', 'しゃしん'), ('撮', 'と')])
        self.assertEqual(res['corrected'], '姉の結婚式で写真を撮った')

    def test_masu_stem_not_after_case_particle(self):
        # まに→にま は ます の字を壊す形（作り｜に｜まし）になるので入れ替えない
        res = self.run_ime('カレーを作りまにした')
        self.assertEqual(res['corrected'], 'カレーを作りまにした')
        self.assertTrue(res['odd_spans'])

    def test_word_then_particle_stays(self):
        # 語＋助詞として読めるかなの並び（びょうき｜を・かみ｜を）は入れ替えない
        self.assertEqual(self.run_ime('かみをきります。')['corrected'], 'かみをきります。')
        self.assertEqual(self.run_ime('びょうきをなおす')['corrected'], '病気を治す')


if __name__ == '__main__':
    unittest.main()
