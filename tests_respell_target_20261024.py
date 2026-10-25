"""IME の読みの1打戻し（_ime_one_key_respell）が正しい行を学習した語へ替えない（2026-10-24・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class RespellTargetTests(unittest.TestCase):
    def run_line(self, text, vocab, ime):
        st = initial()
        for rd, sf, n in vocab:
            for _ in range(n):
                st.store.add(rd, sf)
        for sf, rd in ime:
            st.ime_readings.remember(sf, rd)
        return correct_line(text, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_word_seen_once_is_not_a_target(self):
        # 1回だけ見た語（製する）へは戻さない
        text = '誤字はその場で即補正すると楽だ。'
        r = self.run_line(text, [('せいする', '製する', 1)], [('補正する', 'ほせいする'), ('補正すると', 'ほせいすると')])
        self.assertEqual(r['corrected'], text)

    def test_everyday_face_is_kept(self):
        # 打った読みのいちばん身近な表記（緑＝みどり）は、別の語（戻り）に替えない
        text = '信号が緑、横の線が白です。'
        r = self.run_line(text, [('もどり', '戻り', 2)], [('緑', 'みどり')])
        self.assertEqual(r['corrected'], text)


if __name__ == '__main__':
    unittest.main()
