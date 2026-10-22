"""異様の門は、IME に記録された打った読みだけを開く（2026-10-22・画面の報告から。例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class TypedReadingTests(unittest.TestCase):
    def run_ime(self, face, pairs, words=()):
        st = initial()
        for rd, sf in words:
            for _ in range(3):
                st.store.add(rd, sf)
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_other_kanji_reading_is_not_opened(self):
        # 打った読み しょうまつは（ゅ→ょ）。松 を しょう と読み替えた しょうしょうは からは探さない
        # 本人が 症状 を使っていても、打っていない読みから 症状 に替えない
        got = self.run_ime('翔松は', [('翔松は', 'しょうまつは')], words=[('しょうじょう', '症状')])
        self.assertNotIn('症状', got)


if __name__ == '__main__':
    unittest.main()
