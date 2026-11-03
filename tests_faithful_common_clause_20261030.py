"""打ったとおりに読める確定の文節で、漢字の語がどれも世の中でよく使う語なら、1打を戻した別の語に替えない
（2026-10-30・補正担当。正しい文の ひとつ前は が 人前は に、見ると が 来ると になっていた。例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class FaithfulCommonClauseTests(unittest.TestCase):
    def run_ime(self, face, pairs, words=()):
        st = initial()
        for rd, sf in words:
            for _ in range(3):
                st.store.add(rd, sf)
        for sf, rd in pairs:
            st.ime_readings.remember(sf, rd)
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_common_words_typed_as_read_are_kept(self):
        got = self.run_ime('もうひとつ前の駅で降りた。', [('ひとつ前の', 'ひとつまえの')], words=[('ひとまえ', '人前')])
        self.assertEqual(got, 'もうひとつ前の駅で降りた。')
        got = self.run_ime('ボタンで見ると分かる。', [('見ると', 'みると')], words=[('くる', '来る'), ('くると', '来ると')])
        self.assertEqual(got, 'ボタンで見ると分かる。')

    def test_faithful_clause_with_moved_mark_still_fixed(self):
        got = self.run_ime('あしたから掃除をば占める。', [('ば占める', 'ばしめる')], words=[('はじめる', '始める')])
        self.assertIn('掃除を始める', got)


if __name__ == '__main__':
    unittest.main()
