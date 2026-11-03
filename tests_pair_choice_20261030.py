# -*- coding: utf-8 -*-
"""pair_choice（語の組の回数で同じ読みの名詞の選び違いを疑う・2026-10-30）の試験。"""
import unittest

import pair_choice as P


class PairChoiceTests(unittest.TestCase):
    def test_everyday_lines_are_kept(self):
        for line in ('新しい住所に引っ越した', '朝に新聞を読む', '二人目の子どもが生まれた。',
                     '休日の朝はゆっくり珈琲を飲むのが楽しみだ。', '駅の先頭で待つ'):
            self.assertEqual(P.propose(line), [], line)

    def test_noun_without_its_pair_but_with_a_same_reading_pair_is_purple(self):
        self.assertTrue(P.propose('友達に変心を書く'))

    def test_without_table_nothing_happens(self):
        saved = P._table
        P._table = lambda: None
        try:
            self.assertEqual(P.propose('友達に変心を書く'), [])
        finally:
            P._table = saved


if __name__ == '__main__':
    unittest.main()
