# -*- coding: utf-8 -*-
"""Text 以外の部品の絵文字を色付きで（2026-11-21 うにさん「絵文字を白黒で見せないようにする」）。
CN_EMOJI_WIDGETS=0 で前の形。自分の Tk の窓だけ（画面の外）・作った例文の絵文字だけ。"""
import os
import sys
import time
import tkinter as tk
import unittest
from unittest import mock

import emoji_widgets as W

SMILE = '\U0001F600'
CAT = '\U0001F431'


@unittest.skipUnless(sys.platform == 'win32', 'Windows だけ')
class EmojiWidgets(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        import offscreen_window; offscreen_window.hold(self.root, '400x300')
        self.addCleanup(self.root.destroy)
        import emoji_color
        if emoji_color.renderer() is None:
            self.skipTest('DirectWrite が無い')

    def pump(self, s=0.4):
        end = time.monotonic() + s
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def test_label_gets_colour_image(self):
        lab = tk.Label(self.root, text='メモ' + SMILE, bg='white', fg='black')
        lab.pack()
        self.assertTrue(W.label(lab))
        self.assertTrue(str(lab.cget('image')))
        self.assertEqual(str(lab.cget('text')), 'メモ' + SMILE)          # 字はそのまま持つ

    def test_label_without_emoji_untouched(self):
        lab = tk.Label(self.root, text='メモ')
        lab.pack()
        self.assertFalse(W.label(lab))
        self.assertEqual(str(lab.cget('image')), '')

    def test_listbox_overlays_only_emoji_rows_and_follows_selection(self):
        lb = tk.Listbox(self.root, height=5)
        lb.pack(fill='both', expand=True)
        for t in ('ねこ', 'ねこ' + CAT, 'えがお' + SMILE, 'ふつう'):
            lb.insert('end', t)
        got = W.listbox(lb)
        self.pump()
        self.assertEqual(sorted(got.shown), [1, 2])
        before = got.shown[1][0]
        lb.selection_set(1)
        lb.event_generate('<<ListboxSelect>>')
        self.pump()
        self.assertNotEqual(got.shown[1][0], before)                        # 選んだ色で描き直す

    def test_listbox_click_on_overlay_reaches_listbox(self):
        lb = tk.Listbox(self.root, height=5)
        lb.pack(fill='both', expand=True)
        for t in ('あ', 'い' + CAT):
            lb.insert('end', t)
        hits = []
        lb.bind('<ButtonRelease-1>', lambda e: hits.append(lb.nearest(e.y)))
        got = W.listbox(lb)
        self.pump()
        lab = got.shown[1][1]
        lab.event_generate('<ButtonPress-1>', x=5, y=3)
        lab.event_generate('<ButtonRelease-1>', x=5, y=3)
        self.pump(0.1)
        self.assertEqual(hits, [1])

    def test_underlined_label_and_back_to_text(self):
        from tkinter import font as tkfont
        f = tkfont.Font(root=self.root, family='Yu Gothic UI', size=11, underline=True)
        lab = tk.Label(self.root, text='見出し' + CAT, font=f, bg='white', fg='#1060c0')
        lab.pack()
        self.assertTrue(W.label(lab))
        lab.configure(text='見出し')                                         # 絵文字を消した
        self.assertFalse(W.label(lab))
        self.assertEqual(str(lab.cget('image')), '')

    def test_title_toc_hooks(self):
        import title_toc
        with open(title_toc.__file__, encoding='utf-8') as fh:
            src = fh.read()
        self.assertEqual(src.count('            _emoji_label(link)'), 2)                # 左の目次・右の目次
        self.assertEqual(src.count('        _emoji_text(self.title)'), 2)           # 左のタイトル・右のタイトル

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_EMOJI_WIDGETS': '0'}):
            lab = tk.Label(self.root, text='メモ' + SMILE)
            self.assertFalse(W.label(lab))
            lb = tk.Listbox(self.root)
            self.assertIsNone(W.listbox(lb))

    def test_dropdown_and_f5_window_hook(self):
        import f5_predict_window as F
        with open(F.__file__, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('emoji_widgets.listbox(lb)', src)
        import app
        with open(app.__file__, encoding='utf-8') as fh:
            asrc = fh.read()
        self.assertIn('_emoji_widgets.listbox(lb)', asrc)
        self.assertIn('_emoji_widgets.label(lb)', asrc)


if __name__ == '__main__':
    unittest.main()
