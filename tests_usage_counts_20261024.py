"""補正の各段の使われ方の数（usage_counts・2026-10-24・例文は作った文）"""
import unittest
from tests_analysis_async import initial
import correction_entry
import usage_counts as U


class UsageCountsTests(unittest.TestCase):
    LINES = ('今日は早く寝ます。', 'あしたはしごとがやすみた。', '新しい靴を買った。', 'かいぎのしりょうをつくる。')

    def run_lines(self):
        st = initial()
        return [correction_entry.correct_line(l, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                                              decisions=st.decisions, context_vec=st.context_vec) for l in self.LINES]

    def test_answers_are_the_same_as_unwrapped(self):
        # 包みを外した元の関数で回した答えと、1字も違わない
        wrapped = self.run_lines()
        import corrector, last_keystroke, collocation_repair, romaji_swap_repair
        saved = []
        for mod in (corrector, correction_entry, last_keystroke, collocation_repair, romaji_swap_repair):
            for k, v in list(vars(mod).items()):
                if callable(v) and getattr(v, '_usage_counts', False):
                    saved.append((mod, k, v))
                    setattr(mod, k, v.__wrapped__)
        try:
            plain = self.run_lines()
        finally:
            for mod, k, v in saved:
                setattr(mod, k, v)
        self.assertEqual([(r['corrected'], r['odd_spans']) for r in wrapped], [(r['corrected'], r['odd_spans']) for r in plain])

    def test_three_groups_and_only_counts(self):
        self.run_lines()
        eff, none, unused = U.table()
        self.assertTrue(U.STAGES)
        self.assertEqual(len(eff) + len(none) + len(unused), len(U.snapshot()))
        # 数だけを持つ: 値は2つの整数、鍵は段の名前（行の中身は入らない）
        for n, c in U.snapshot().items():
            self.assertTrue(isinstance(c, list) and len(c) == 3 and all(isinstance(x, int) for x in c))
            self.assertFalse(any(l in n for l in self.LINES))

    def test_merge_reads_counts_only(self):
        before = U.snapshot().get('x.y', [0, 0, 0])
        U.merge({'x.y': [5, 3, 1], 'bad': ['a', 1, 0], 'odd': [1, 2, 0], 'text': '今日は'})
        self.assertEqual(U.COUNTS['x.y'], [before[0] + 5, before[1] + 3, before[2] + 1])
        self.assertNotIn('odd', U.COUNTS)
        self.assertNotIn('bad', U.COUNTS)
        self.assertNotIn('text', U.COUNTS)


if __name__ == '__main__':
    unittest.main()
