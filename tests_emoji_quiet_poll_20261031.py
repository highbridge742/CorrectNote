# -*- coding: utf-8 -*-
"""絵文字の色の見張り（emoji_color の 90ms ごとの確かめ）は、欄に絵文字が1つも無く、何も出していないあいだは
何もしない（2026-10-31: 何もしていないときの本体の CPU の大半だった）。欄が変わるたびに探し直す。"""
import sys
import unittest
import tkinter as tk

import emoji_color


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class EmojiQuietPollTests(unittest.TestCase):
    E = '\U0001F600'

    def setUp(self):
        from analysis_work import observe_text
        self.root = tk.Tk()
        self.root.geometry('400x200+0+0')
        self.w = tk.Text(self.root)
        self.w.pack(fill='both', expand=True)
        observe_text(self.w)
        self.overlay = emoji_color.install(self.w)
        if self.overlay is None:
            self.skipTest('colour emoji are not available here')
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_plain_text_needs_nothing_and_an_edit_brings_it_back(self):
        o = self.overlay
        self.w.insert('1.0', 'ふつうの文です\n二行目')
        self.root.update()
        self.assertTrue(o._nothing_to_show())
        self.w.insert('end', 'ここに' + self.E)
        self.assertFalse(o._nothing_to_show())
        self.root.update()
        o._tick()
        self.assertTrue(o.shown or o._skipped or (o._hidden and o._hidden[2]))
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', 'また文字だけ')
        self.root.update()
        o._tick()                      # what was laid over the old emoji is taken away first
        self.assertEqual(o.shown, [])
        self.assertTrue(o._nothing_to_show())

    def test_an_emoji_far_below_the_screen_still_counts(self):
        self.w.insert('1.0', '行\n' * 500 + self.E)
        self.root.update()
        self.assertFalse(self.overlay._nothing_to_show())


if __name__ == '__main__':
    unittest.main()
