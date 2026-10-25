"""IME の塊の頭に助詞1字が付いた形（の下）を、学習した語へ1打で戻さない（2026-10-24・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class HeadParticleTests(unittest.TestCase):
    def setUp(self):
        self.st = initial()
        # 学習で 真下（ました）が立ち、IME で の下に（のしたに）と打った記録がある状態
        for _ in range(2):
            self.st.store.add('ました', '真下')
        for sf, rd in (('下', 'した'), ('の下に', 'のしたに'), ('下に', 'したに')):
            self.st.ime_readings.remember(sf, rd)

    def correct(self, text):
        st = self.st
        return correct_line(text, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_noun_no_position_is_kept(self):
        for text in ('「お知らせ」の下にする', '「目次」の下にする'):
            r = self.correct(text)
            self.assertEqual(r['corrected'], text)
            self.assertEqual(r['odd_spans'], [])


    def test_respell_does_not_swallow_tail_particle(self):
        # 語＋助詞の塊（以下は）を、助詞をまたいで1打戻した語（会派）に替えない
        st = initial()
        for _ in range(2):
            st.store.add('かいは', '会派')
        st.ime_readings.remember('以下は', 'いかは')
        text = '以下は手順の例です。'
        r = correct_line(text, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                         decisions=st.decisions, context_vec=st.context_vec)
        self.assertEqual(r['corrected'], text)


if __name__ == '__main__':
    unittest.main()
