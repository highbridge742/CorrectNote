# -*- coding: utf-8 -*-
"""検索の目印をまとめて付ける（emphasis_font.apply_many・2026-11-02）。1件ごとに全部のタグへ尋ねていて、よく出る字で
「次を検索」のたびに窓が 2.4秒止まっていた → 0.09秒。字ごとの大きさの切れ目は今までと同じ。"""
import tkinter as tk
import unittest

import emphasis_font as E


class ApplyManyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root, font=('Arial', 10))
        self.text.insert('1.0', '今日の天気はよいの😀の\n別の行の文の')
        self.text.tag_configure('big', font=('Arial', 14))
        self.text.tag_configure('small', font=('Arial', 8))
        self.text.tag_configure('plain')
        self.text.tag_add('big', '1.0', '1.3')
        self.text.tag_add('small', '1.3', '1.5')
        self.text.tag_add('plain', '1.0', '2.0')

    def tearDown(self):
        self.root.destroy()

    def sizes(self):
        out = {}
        for tag in self.text.tag_names():
            if tag.startswith('emph_find'):
                size = self.text.tag_cget(tag, 'font').split()[-1]
                ranges = [str(i) for i in self.text.tag_ranges(tag)]
                out[size] = out.get(size, []) + ranges
        return out

    def test_a_range_is_cut_where_the_font_changes(self):
        self.assertEqual(E.apply_many(self.text, [('1.1', '1.4')], 2, 'emph_find'), 2)
        self.assertEqual(self.sizes(), {'28': ['1.1', '1.3'], '16': ['1.3', '1.4']})

    def test_many_ranges_equal_one_by_one(self):
        ranges = [('1.2', '1.3'), ('1.8', '1.9'), ('2.3', '2.4'), ('1.1', '1.4')]
        self.assertEqual(E.apply_many(self.text, ranges, 1.5, 'emph_find'), 5)
        many = {k: sorted(v) for k, v in self.sizes().items()}
        E.clear(self.text, 'emph_find')
        for a, z in ranges:
            E.apply(self.text, a, z, 1.5, 'emph_find')
        self.assertEqual({k: sorted(v) for k, v in self.sizes().items()}, many)

    def test_a_batch_asks_tk_little(self):
        calls = []
        real = self.text.tag_nextrange
        self.text.tag_nextrange = lambda *a: calls.append(a) or real(*a)
        E.apply_many(self.text, [('1.8', '1.9')] * 20, 1.5, 'emph_find')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
