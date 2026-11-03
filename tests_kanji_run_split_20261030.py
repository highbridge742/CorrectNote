"""漢字の連なりの一部だけの文節を、かなの入る語に替えて複合語を割らない（2026-10-30・補正担当。例文は作った文）"""
import unittest
import last_keystroke as L


class KanjiRunSplitTests(unittest.TestCase):
    def test_tail_of_compound_to_kana_word_splits(self):
        line = 'この数列は長い。'
        self.assertTrue(L._splits_kanji_run(line, 3, 4, {'corrected': 'この数連れは長い。'}))

    def test_kanji_for_kanji_is_not_a_split(self):
        line = 'この数列は長い。'
        self.assertFalse(L._splits_kanji_run(line, 3, 4, {'corrected': 'この数例は長い。'}))

    def test_whole_kanji_run_is_not_a_split(self):
        line = 'この列は長い。'
        self.assertFalse(L._splits_kanji_run(line, 2, 3, {'corrected': 'この連れは長い。'}))

    def test_gate_is_wired_in_clause_repair(self):
        import inspect
        src = inspect.getsource(L.repair_ime_clause)
        self.assertIn('_splits_kanji_run(line, row[1], row[2], row[4])', src)


if __name__ == '__main__':
    unittest.main()
