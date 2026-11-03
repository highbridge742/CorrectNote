"""直しの跡の隣で見送った品詞のつながりの紫を、直した行の上でも見る（2026-10-30・補正担当。例文は作った文）"""
import unittest
import correction_entry as C


class FixedLineConnectionTests(unittest.TestCase):
    def test_noun_then_passive_tail_beside_fix(self):
        line = 'がっこうに町れかかる。'
        got = C._mark_impossible_connections(line, {'corrected': '学校に町れかかる。', 'original_spans': [[0, 4]],
                                                     'spans': [[0, 2]], 'odd_spans': []})
        self.assertIn((5, 7), [tuple(x[:2]) for x in got.get('odd_spans') or ()])

    def test_correct_rest_gets_no_mark(self):
        got = C._mark_impossible_connections('がっこうに町へ行く。', {'corrected': '学校に町へ行く。', 'original_spans': [[0, 4]],
                                                                   'spans': [[0, 2]], 'odd_spans': []})
        self.assertFalse(got.get('odd_spans'))


if __name__ == '__main__':
    unittest.main()
