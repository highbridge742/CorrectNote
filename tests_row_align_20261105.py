# -*- coding: utf-8 -*-
"""Two places far apart changed at once: the rows between them keep their answers, those near a change do not. No window."""
import unittest

import row_align as R
from context_vec import nearby_reanalysis_lines


def rows(n):
    return ['row %d' % k for k in range(n)]


def common(old, new):
    head = 0
    while head < min(len(old), len(new)) and old[head] == new[head]:
        head += 1
    tail = 0
    while tail < min(len(old), len(new)) - head and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    return head, tail


class Carried(unittest.TestCase):
    def test_rows_between_two_changes_are_found(self):
        old = rows(100)
        new = list(old); new[5] = 'changed a'; new[60] = 'changed b'
        head, tail = common(old, new)
        got = R.carried_rows(old, new, head, tail)
        self.assertEqual(head, 5)
        for k in range(6, 60):
            self.assertEqual(got[k], k)
        self.assertNotIn(5, got)
        self.assertNotIn(60, got)

    def test_rows_that_moved_are_followed(self):
        old = rows(50)
        new = old[:5] + old[6:30] + ['new one', 'new two'] + old[30:]
        head, tail = common(old, new)
        got = R.carried_rows(old, new, head, tail)
        for now, before in got.items():
            self.assertEqual(new[now], old[before])
        self.assertEqual(got[new.index('row 20')], 20)
        self.assertNotIn(new.index('new one'), got)

    def test_ordinary_edits_are_left_alone(self):
        old = rows(20)
        new = list(old); new[5] = 'changed'
        self.assertEqual(R.carried_rows(old, new, *common(old, new)), {})
        new = list(old); new[5] = 'a'; new[6] = 'b'; new[7] = 'c'
        self.assertEqual(R.carried_rows(old, new, *common(old, new)), {})

    def test_a_very_wide_middle_is_left_alone(self):
        old = rows(R.MAX_MIDDLE + 10)
        new = list(old); new[1] = 'a'; new[-2] = 'b'
        self.assertEqual(R.carried_rows(old, new, *common(old, new)), {})

    def test_repeated_rows_keep_the_order(self):
        old = ['', 'x', '', 'x', '', 'x', '', 'x', '']
        new = ['a', 'x', '', 'x', '', 'x', '', 'x', 'b']
        got = R.carried_rows(old, new, *common(old, new))
        self.assertEqual(sorted(got.values()), sorted(set(got.values())))
        keys = sorted(got)
        self.assertEqual([got[k] for k in keys], sorted(got[k] for k in keys))


class Near(unittest.TestCase):
    def test_a_change_inside_acts_as_a_single_edit_would(self):
        # Rows around each change, as nearby_reanalysis_lines gives for that change by itself
        old = rows(100)
        new = list(old); new[5] = 'a'; new[50] = 'b'; new[90] = 'c'
        head, tail = common(old, new)
        carried = R.carried_rows(old, new, head, tail)
        radius = 3
        near = set(R.near_changes(carried, head, len(new) - tail, len(new), radius))
        alone = set(nearby_reanalysis_lines(50, 49, 100, 100, radius=radius))
        self.assertTrue(alone <= near, sorted(alone - near))
        self.assertTrue(set(range(6, 9)) <= near)
        self.assertTrue(set(range(87, 90)) <= near)
        # and the far rows stay
        self.assertNotIn(30, near)
        self.assertNotIn(70, near)

    def test_a_row_taken_away_inside_counts_too(self):
        old = rows(60)
        new = old[:5] + ['a'] + old[6:30] + old[31:55] + ['b'] + old[56:]
        head, tail = common(old, new)
        carried = R.carried_rows(old, new, head, tail)
        near = set(R.near_changes(carried, head, len(new) - tail, len(new), 3))
        gone = new.index('row 31')
        self.assertIn(gone, near)
        self.assertIn(gone - 1, near)
        self.assertNotIn(gone + 10, near)


if __name__ == '__main__':
    unittest.main()
