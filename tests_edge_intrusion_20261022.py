"""余分な1打の戻しを、脱字の戻しより先に見る（2026-10-22・画面の報告から。例文は作った文）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class EdgeIntrusionTests(unittest.TestCase):
    def run_line(self, line):
        st = initial()
        return correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_extra_key_before_small_kana_is_removed(self):
        # しとゅう の と は し の隣のキー。ゅう の前に し を足す（しとしゅう）より、と を抜く
        self.assertEqual(self.run_line('友達としとゅうがく旅行に行く'), '友達と修学旅行に行く')


if __name__ == '__main__':
    unittest.main()
