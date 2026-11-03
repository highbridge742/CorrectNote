# -*- coding: utf-8 -*-
"""候補一覧が伸びても元の行を隠さない（計算だけ・2026-11-03）。"""
import unittest
from app import fit_dropdown

PAD, ROW = 4, 20


def fit(count, anchor, above=False, top=0, bottom=1000):
    return fit_dropdown(count, anchor, top, bottom, PAD, ROW, above=above, gap=24)


class Fit(unittest.TestCase):
    def test_room_below_stays_below(self):
        self.assertEqual(fit(5, 100), (5, False))

    def test_no_room_below_goes_above(self):
        self.assertEqual(fit(10, 900), (10, True))

    def test_growing_moves_it_above(self):
        self.assertEqual(fit(3, 900), (3, False))
        self.assertEqual(fit(8, 900), (8, True))

    def test_once_above_it_stays_above_when_it_shrinks(self):
        self.assertEqual(fit(2, 900, above=True), (2, True))

    def test_too_tall_for_both_uses_the_wider_side_and_scrolls(self):
        rows, above = fit(100, 700)
        self.assertTrue(above)
        self.assertEqual(rows, (700 - 24 - PAD) // ROW)
        rows, above = fit(100, 300)
        self.assertFalse(above)
        self.assertEqual(rows, (1000 - 300 - PAD) // ROW)

    def test_already_above_keeps_to_the_upper_side(self):
        rows, above = fit(100, 300, above=True)
        self.assertTrue(above)
        self.assertEqual(rows, (300 - 24 - PAD) // ROW)

    def test_never_covers_the_row(self):
        for anchor in range(40, 1000, 37):
            for count in (1, 5, 30, 200):
                for start in (False, True):
                    rows, above = fit(count, anchor, above=start)
                    height = PAD + rows * ROW
                    if rows > 1:
                        if above:
                            self.assertLessEqual(height, anchor - 24)
                        else:
                            self.assertLessEqual(anchor + height, 1000)

    def test_at_least_one_row(self):
        self.assertEqual(fit(5, 30, top=20, bottom=40)[0], 1)


if __name__ == '__main__':
    unittest.main()
