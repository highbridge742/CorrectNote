# -*- coding: utf-8 -*-
"""The line-number gutter finds the spaced rows (navigation_head/tail at the row start) from the two tags' ranges,
the same rows tag_names at each row start gave (2026-11-07, speed). Opens a small window."""
import random
import tkinter as tk
import unittest

import app


class NavRows(unittest.TestCase):
    def test_the_same_rows_as_asking_each_row(self):
        root = tk.Tk(); root.withdraw()
        try:
            t = tk.Text(root)
            t.insert('1.0', '\n'.join(('行%d' % k) * (k % 4) for k in range(80)))
            rnd = random.Random(5)
            for rep in range(40):
                for tag in ('navigation_head', 'navigation_tail'):
                    t.tag_remove(tag, '1.0', 'end')
                    for _ in range(rnd.randint(0, 4)):
                        a = '%d.%d' % (rnd.randint(1, 80), rnd.randint(0, 5))
                        b = '%d.%d' % (rnd.randint(1, 81), rnd.randint(0, 5))
                        if t.compare(a, '<', b):
                            t.tag_add(tag, a, b)
                want = {r for r in range(1, 82)
                        if any(tag in t.tag_names('%d.0' % r) for tag in ('navigation_head', 'navigation_tail'))}
                got = app.LineNumberGutter._navigation_rows(t)
                self.assertEqual({r for r in got if r <= 81}, want, rep)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
