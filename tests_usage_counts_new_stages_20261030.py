"""後から足した補正の段（10-25〜30）も、使われた数を段ごとに数える（2026-10-30・補正担当）"""
import inspect
import unittest
import correction_entry
import usage_counts


class UsageCountsNewStagesTests(unittest.TestCase):
    def test_new_stages_listed_and_exist(self):
        src = inspect.getsource(usage_counts.install)
        for attr in ('_lattice_place', '_word_pair_mark', '_renyou_tail_slip', '_degree_adverb', '_dangling_verb',
                     '_impossible_slip', '_kanji_doubt', '_ime_reconvert', '_honorific_stem', '_pair_choice',
                     '_nearby_one_key'):
            self.assertIn(repr(attr), src)
            self.assertTrue(callable(getattr(correction_entry, attr, None)), attr)


if __name__ == '__main__':
    unittest.main()
