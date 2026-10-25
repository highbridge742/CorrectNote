"""確定した文節を行の上で読み直す（設計30 の4つ目の口・2026-10-23・例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class ImeClauseLineTests(unittest.TestCase):
    def run_ime(self, face, pairs, words=()):
        st = initial()
        for rd, sf in words:
            for _ in range(3):
                st.store.add(rd, sf)
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_faithful_clause_with_moved_mark(self):
        # はじめる の ゛ が前の字に付いた ばしめる を、IME がそのまま ば占める にした
        got = self.run_ime('あしたから掃除をば占める。', [('ば占める', 'ばしめる')], words=[('はじめる', '始める')])
        self.assertIn('掃除を始める', got)

    def test_correct_compound_is_kept(self):
        # 打ったとおりの読みの複合語は触らない
        got = self.run_ime('これは明確性です。', [('明確性', 'めいかくせい')])
        self.assertEqual(got, 'これは明確性です。')


if __name__ == '__main__':
    unittest.main()
