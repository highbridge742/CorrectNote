"""数字のあとの、かなの数え方（2026-10-16・`pos_grammar.odd_kana_spans`）。

数字の直後の かなの助数詞（5こ・3つ・4ど）は数え方で、その先が
かなの並びの頭になる（補正の入口の 48-TG と同じ）。助数詞を並びの頭に
含めて「説明が付かない」とし、正しい文を 5こうります・5こうった・
5こすります に直していた。助数詞のあとが説明の付く並びなら印を
立てない。助数詞のあとが乱れていれば、今までどおり印を立てる。

ここの例はすべて作った文。
"""
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class DigitCounterTests(unittest.TestCase):
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

    def odd(self, line):
        from pos_grammar import odd_kana_spans
        return odd_kana_spans(line, self.state.dict_index, self.state.store)

    def test_counted_kana_is_not_marked_or_changed(self):
        for line in ('りんごが5こあります。', 'ぜんぶで5こあった。', '5こいります。',
                     '4どあった。', 'ぜんぶで12こあるはずです。', '５こあります。'):
            with self.subTest(line=line):
                self.assertEqual(self.odd(line), [])
                result = self.run_line(line)
                self.assertEqual(result['corrected'], line)
                self.assertEqual(result['odd_spans'], [])

    def test_each_counter_reading_is_tried(self):
        # つう（通）で切ると残りが けとりました になる。つ で切れば説明が付く
        self.assertEqual(self.odd('3つうけとりました。'), [])

    def test_broken_kana_after_a_counter_is_still_marked(self):
        for line in ('りんごが5こあろます。', '5こあるますか。'):
            with self.subTest(line=line):
                self.assertTrue(self.odd(line))
                self.assertTrue(self.run_line(line)['odd_spans'])


if __name__ == '__main__':
    unittest.main()
