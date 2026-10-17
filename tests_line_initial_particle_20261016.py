"""行頭の格助詞のあとに完結した述語がある行（2026-10-16・`contextual_repair.validate`）。

前の行の続きとして、行が助詞で始まることがある（になります・にします）。
助詞を語の一部として読む直し（のひっています → 残っています）だけを採り、
行頭の1字を消す・替える・動かすだけの直しは採らない。

ここの例はすべて作った文。
"""
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class LineInitialParticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def setUp(self):
        from last_choice import set_active
        self.addCleanup(set_active, None)

    def run_line(self, line):
        from correction_entry import correct_line
        a = self.state
        return correct_line(line, a.store, context_vocab={}, input_method='kana',
                            dict_index=a.dict_index, decisions=a.decisions,
                            context_vec=a.context_vec)

    def test_line_initial_particle_is_not_removed_or_replaced(self):
        for line in ('になります。', 'にします'):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line)['corrected'], line)

    def test_particle_read_into_a_word_is_still_repaired(self):
        self.assertEqual(self.run_line('のひっています')['corrected'], '残っています')


if __name__ == '__main__':
    unittest.main()
