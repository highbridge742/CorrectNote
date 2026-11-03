# -*- coding: utf-8 -*-
"""impossible_slip は決まった形も置かず紫だけ（例文の組で決まる助詞は置く）（2026-11-01 手分けB）。作った例だけ。"""
import unittest
import impossible_slip as I


class PurpleOnlyTests(unittest.TestCase):
    def setUp(self):
        self._propose, self._second = I.propose, I.second_opinion

    def tearDown(self):
        I.propose, I.second_opinion = self._propose, self._second

    def test_found_shape_becomes_purple(self):
        line = 'ほんをよむたった'
        I.propose = lambda text, *a, **k: [(5, 6, 'ん')]
        out = I.repair_line(line, {'corrected': line, 'odd_spans': []})
        self.assertEqual(out['corrected'], line)
        self.assertIn((5, 6), [tuple(x[:2]) for x in out['odd_spans']])

    def test_second_opinion_only_marks(self):
        line = 'ほんをよんた'
        done = 'ほんをよんだ'
        I.second_opinion = lambda l, d: 'ほんをよんで'
        out = I.repair_line(line, {'corrected': done, 'odd_spans': []})
        self.assertEqual(out['corrected'], done)
        self.assertTrue(out['odd_spans'])

    def test_flag(self):
        self.assertFalse(I.DECIDE)


if __name__ == '__main__':
    unittest.main()
