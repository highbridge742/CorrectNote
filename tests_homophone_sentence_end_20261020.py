# -*- coding: utf-8 -*-
"""同音の対の表（設計35）が選んだ形は、文末の名詞を守る門（incomplete_original_source）で止めない（うに 2026-10-20 01:44Z）。"""
import unittest
import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class HomophoneSentenceEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def correct(self, line):
        import app
        a = self.state
        return app.correct_line(line, a.store, input_method='kana', dict_index=a.dict_index,
                                decisions=a.decisions, context_vec=a.context_vec)

    def test_pair_table_choice_passes_the_sentence_end_gate(self):
        for line, want in (('荷物が思い。', '荷物が重い。'), ('荷物が思い', '荷物が重い'),
                           ('荷物が思いので持てない。', '荷物が重いので持てない。')):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line)['corrected'], want)

    def test_lines_without_the_pair_cue_are_kept(self):
        for line in ('それが私の思い。', '家族への思い。', '荷物が重い。', '気持ちを思い出す。'):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line)['corrected'], line)


if __name__ == '__main__':
    unittest.main()
