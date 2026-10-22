"""IME の顔の漢字に戻す直し（2026-10-21・隣接キー1打の総当たりから。例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class KeptKanjiTests(unittest.TestCase):
    def run_ime(self, face, pairs):
        st = initial()
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_extra_key_after_kept_kanji_is_dropped(self):
        # 食べ＋たふ の IME の顔 食べタフ は、漢字 食 を残したまま 食べた に戻す
        self.assertEqual(self.run_ime('昼ご飯を食べタフ', [('食べタフ', 'たべたふ')]), '昼ご飯を食べた')

    def test_extra_key_in_particle_after_kanji(self):
        # 猫＋かぎ（が＋き）の顔 猫鍵 は、漢字 猫 を残して 猫が に戻す
        self.assertEqual(self.run_ime('犬鍵庭で寝ている', [('犬鍵', 'いぬかぎ')]), '犬が庭で寝ている')

    def test_correct_line_is_untouched(self):
        self.assertEqual(self.run_ime('昼ご飯を食べた', []), '昼ご飯を食べた')


if __name__ == '__main__':
    unittest.main()
