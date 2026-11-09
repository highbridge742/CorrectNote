# -*- coding: utf-8 -*-
"""The purple found half way is shown before the answer, then the answer draws its own (2026-11-06). Opens a small window."""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace

import early_marks as E
from analysis_worker import Worker


class Partials(unittest.TestCase):
    def test_kept_apart_from_answers_and_dropped_when_old(self):
        w = Worker.__new__(Worker)
        w.partials = {3: [dict(odd=[(0, 2)])], 1: [dict(odd=[(1, 2)])]}
        self.assertEqual(w.take_partial(3), [dict(odd=[(0, 2)])])
        self.assertEqual(w.partials, {})          # an older request's partials go too
        self.assertEqual(w.take_partial(3), ())


class Paint(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.t = tk.Text(self.root)
        self.t.tag_configure('odd', background='#c0a0e0')
        self.t.insert('1.0', '一行目\nかいぎのじゅんび\n三行目')
        self.app = SimpleNamespace(editor=self.t, settings={'show_odd': True}, decisions=None)

    def tearDown(self):
        self.root.destroy()

    def test_painted_on_the_row_then_cleared(self):
        self.assertTrue(E.memo(self.app, 1, dict(line='かいぎのじゅんび', odd=[(0, 4)])))
        self.assertEqual([str(x) for x in self.t.tag_ranges(E.TAG)], ['2.0', '2.4'])
        self.assertEqual(self.t.tag_cget(E.TAG, 'background'), '#c0a0e0')
        self.assertEqual(self.t.tag_ranges('odd'), ())       # the answer's own tag is not touched
        E.clear_memo(self.app, 1)
        self.assertEqual(self.t.tag_ranges(E.TAG), ())

    def test_not_painted_when_the_row_changed(self):
        self.assertFalse(E.memo(self.app, 1, dict(line='べつの文', odd=[(0, 2)])))
        self.assertEqual(self.t.tag_ranges(E.TAG), ())

    def test_not_painted_when_marks_are_off_or_switched_off(self):
        self.app.settings = {'show_odd': False}
        self.assertFalse(E.memo(self.app, 1, dict(line='かいぎのじゅんび', odd=[(0, 4)])))
        self.app.settings = {'show_odd': True}
        os.environ['CN_EARLY_ODD'] = '0'
        try:
            self.assertFalse(E.memo(self.app, 1, dict(line='かいぎのじゅんび', odd=[(0, 4)])))
        finally:
            del os.environ['CN_EARLY_ODD']

    def test_quick_input_shows_no_purple_only_marks_so_none_early(self):
        app = SimpleNamespace(_quick_text=self.t, decisions=None)
        self.assertFalse(E.quick(app, dict(row=1, line='かいぎのじゅんび', odd=[(0, 4)])))


if __name__ == '__main__':
    unittest.main()
