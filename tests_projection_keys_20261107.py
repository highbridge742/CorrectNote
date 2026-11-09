# -*- coding: utf-8 -*-
"""update_tag works out plain 'R.C' / 'R.0+Nc' positions itself (2026-11-07, speed); they must be what Tk's
index gives, and the tags it leaves must be the same as before. Opens a small window."""
import random
import tkinter as tk
import unittest
from unittest.mock import patch

import ui_projection as P


ROWS = ['今日は朝から雨が降っていた。', '', 'abc', '絵文字😀のある行😀です', 'がﾞ合成゛の字',
        'とても長い行' * 30, 'x', '🙂', '最後の行']


class Keys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.t = tk.Text(cls.root)
        cls.t.insert('1.0', '\n'.join(ROWS))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_the_same_as_tk(self):
        t = self.t
        keys = P._Keys(t, t.get('1.0', 'end-1c'))
        forms = ['end', 'end-1c', '1.0+3c lineend', '2.end', 'insert']
        for row in range(0, len(ROWS) + 3):
            for col in (0, 1, 2, 5, 7, 8, 9, 13, 14, 15, 40, 179, 180, 181, 500):
                forms += ['%d.%d' % (row, col), '%d.0+%dc' % (row, col)]
        rnd = random.Random(7)
        forms += ['%d.0+%dc' % (rnd.randint(1, 9), rnd.randint(0, 200)) for _ in range(300)]
        for form in forms:
            self.assertEqual(keys(form), P._key(t.index(form)), form)

    def test_update_tag_leaves_the_same_tags(self):
        t = self.t
        rnd = random.Random(3)
        for rep in range(30):
            ranges = []
            for _ in range(rnd.randint(0, 40)):
                row = rnd.randint(1, len(ROWS))
                a, b = sorted((rnd.randint(0, 200), rnd.randint(0, 200)))
                ranges.append(('%d.0+%dc' % (row, a), '%d.0+%dc' % (row, b)))
            for tag in ('new', 'old'):
                t.tag_remove(tag, '1.0', 'end')
            # the way it was before: every position from Tk (the same function with Tk's index)
            t._projection_tag_ranges = None
            with patch.object(P, '_Keys', lambda widget, text: (lambda index: P._key(widget.index(index)))):
                P.update_tag(t, 'old', ranges, lambda w, i: i)
            t._projection_tag_ranges = None
            P.update_tag(t, 'new', ranges, lambda w, i: i)
            self.assertEqual(t.tag_ranges('new'), t.tag_ranges('old'), (rep, ranges))


if __name__ == '__main__':
    unittest.main()
