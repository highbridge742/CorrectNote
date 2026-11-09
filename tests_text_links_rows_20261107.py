# -*- coding: utf-8 -*-
"""An edit that adds or removes rows moves the link rows instead of going over the whole text (2026-11-07,
うにさん「エンターを押しっぱなしにして連続で改行を入れる動作が重い」). The tags and links it leaves are the
same as a full pass over the text. Opens a small window."""
import random
import tkinter as tk
import unittest

from analysis_work import observe_text
from text_links import TextLinks

URI = 'data:image/png;base64,' + 'iVBORw0KGgo' * 40


def rows(n, rnd):
    out = []
    for k in range(n):
        kind = rnd.randrange(5)
        out.append('作り物の行 %d です' % k if kind < 2 else
                   'ここ https://example.com/p%d を見る' % k if kind == 2 else
                   URI if kind == 3 else '')
    return out


class Rows(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('500x300+40+40')
        self.t = tk.Text(self.root, wrap='char')
        self.t.pack(fill='both', expand=True)
        observe_text(self.t)
        self.links = TextLinks(self.t)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def state(self):
        self.root.update()
        return ({tag: tuple(map(str, self.t.tag_ranges(tag)))
                 for tag in (TextLinks.TAG, TextLinks.UNWRAPPED_TAG, TextLinks.ELIDED_TAG)},
                {r: [(a, b) for a, b, _l in v] for r, v in self.links._rows.items()},
                dict(self.links._unwrapped_rows))

    def full(self):
        self.links.changed(None)          # the whole text, as before
        return self.state()

    def test_random_row_edits_leave_what_a_full_pass_leaves(self):
        rnd = random.Random(11)
        self.t.insert('1.0', '\n'.join(rows(60, rnd)))
        self.root.update()
        followed = []
        real = self.links._follow_rows
        self.links._follow_rows = lambda *a: followed.append(real(*a)) or followed[-1]
        for step in range(120):
            count = int(self.t.index('end-1c').split('.')[0])
            row = rnd.randint(1, count)
            kind = rnd.randrange(4)
            if kind == 0:
                self.t.insert('%d.end' % row, '\n')                                  # Enter at a row end
            elif kind == 1:
                self.t.insert('%d.0' % row, '\n'.join(rows(rnd.randint(1, 3), rnd)) + '\n')   # a pasted block
            elif kind == 2 and count > 3:
                last = min(count, row + rnd.randint(1, 3))
                self.t.delete('%d.0' % row, '%d.0' % last)                            # rows taken away
            else:
                self.t.insert('%d.0+2c' % row, 'x\nhttps://example.org/n%d y' % step)  # a row split with a link
            got = self.state()
            self.assertEqual(got, self.full(), step)

        self.assertGreater(sum(map(bool, followed)), 60, followed)     # the row-following path was taken


if __name__ == '__main__':
    unittest.main()
