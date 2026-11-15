# -*- coding: utf-8 -*-
"""boundary_colors の bare()（品詞のタグが無い行か）を、窓ごとに dump 1回で見る形にした（2026-11-15 1打で tag nextrange を
約590回呼んでいた）。前の tag nextrange の形と、どの行でも同じ答えを出すこと。自分の Tk の窓だけ。作った例文。"""
import random
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import body_index
import boundary_colors as BC

TAGS = ('pos_a', 'pos_b', 'pos_c', 'pos_none')


class SameRows(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def make(self, header):
        t = tk.Text(self.root)
        if header:
            body_index.install(t, 3)
            t.tk.call(t._cn_body_raw, 'insert', '1.0', '題\n目次\n線\n')
            t.tk.call(t._cn_body_raw, 'tag', 'add', 'pos_a', '1.0', '1.1')      # 見出しの中のタグは本文の行に数えない
        rnd = random.Random(7)
        t.insert('1.0', '\n'.join('行%d の文です。今日は晴れ。' % k for k in range(1, 301)))
        for row in range(1, 301):
            for tag in TAGS[:3]:
                if rnd.random() < 0.15:
                    a = rnd.randrange(0, 10)
                    t.tag_add(tag, '%d.%d' % (row, a), '%d.%d' % (row, a + rnd.randrange(1, 4)))
        return t

    def answers(self, t, dump):
        owner = NS(widget=t, _row_tags=lambda: [(tag, 'x') for tag in TAGS])
        with mock.patch.object(BC, 'DUMP_WINDOW', dump):
            bare = BC.BoundaryColors._bare_rows(owner, span=16)
            return [bare(row) for row in range(1, 301)]

    def test_same_as_nextrange(self):
        for header in (False, True):
            t = self.make(header)
            self.assertEqual(self.answers(t, True), self.answers(t, False), header)

    def test_untagged_text(self):
        t = tk.Text(self.root)
        t.insert('1.0', 'あ\nい\nう')
        self.assertEqual(self.answers(t, True)[:3], [True, True, True])


if __name__ == '__main__':
    unittest.main()
