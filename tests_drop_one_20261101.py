# -*- coding: utf-8 -*-
"""紫の1字を余分に打った形（所ごと抜いた行）も候補にする（odd_respell._drop_candidate・2026-11-01 B）。作った例だけ。"""
import unittest
import odd_respell as O


class DropCandidateTests(unittest.TestCase):
    def test_one_kana_next_to_neighbour_key(self):
        # ち は前の た のキーの隣
        line = '本を読み終わった地'
        got = O._drop_candidate(line, 8, 9, ['ち'])
        self.assertIsNotNone(got)
        self.assertEqual(got[1], '本を読み終わった')
        self.assertEqual(got[2], '')

    def test_far_key_is_not_dropped(self):
        line = '本を読み終わった地'
        self.assertIsNone(O._drop_candidate(line, 8, 9, ['め']))

    def test_long_reading_is_not_dropped(self):
        line = '本を読み終わった地図'
        self.assertIsNone(O._drop_candidate(line, 8, 10, ['ちず']))


if __name__ == '__main__':
    unittest.main()
