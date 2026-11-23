# -*- coding: utf-8 -*-
"""カーソル移動・再入力変換を始めた時の入力カーソルの強調（editor_guides）を、地の明るい配色では白地で見やすくする
（2026-11-23 うにさん「ライトモードでのオレンジのカーソル強調が見えにくいので、白に合わせた調整を入れる」）。
・地の明るい配色（light・matcha・sora）: 強調の色は地とのコントラスト比 4.5 以上、強調の間だけ入力カーソルを太く（3px）
・ダーク系（dark・yoru・sumi）: 今までの #ee963e・太さも変えない
・強調が終われば、色・点滅・太さは元へ戻る。配色を替えた後も、その時の地の色で選ぶ
CN_CARET_FLASH_LIGHT=0 で前の形。自分の Text の窓だけ。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import app
import appearance
import editor_guides as G


def pane_colors(theme):
    pal, dark = appearance.theme_palette(theme, app.LIGHT_PALETTE, app.DARK_PALETTE, app.FIXED_FG)
    return pal['PANEL'], pal['RESULT_BG'], dark


class FlashOnThemes(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root, insertwidth=2, insertofftime=300, insertbackground='#222222')
        self.w.pack()

    def test_contrast_on_every_theme(self):
        got = {}
        for theme in appearance.THEME_ORDER:
            editor_bg, result_bg, dark = pane_colors(theme)
            for bg in (editor_bg, result_bg):
                self.w.configure(background=bg)
                color, width = G.flash_style(self.w)
                ratio = G.contrast(self.w, color, bg)
                got[(theme, bg)] = (color, width, round(ratio, 2))
                if dark:
                    self.assertEqual((color, width), (G.FLASH_COLOR, None), got)          # ダーク系は今のまま
                else:
                    self.assertGreaterEqual(ratio, 4.5, got)                              # 地とのコントラスト比
                    self.assertEqual(width, 3, got)
        # 前の色は白地で見えにくかった（数値で）
        self.w.configure(background='#ffffff')
        self.assertLess(G.contrast(self.w, G.FLASH_COLOR, '#ffffff'), 3.0)
        self.assertGreaterEqual(G.contrast(self.w, G.FLASH_COLOR_LIGHT, '#ffffff'), 4.5)
        print('contrast', got)

    def flash_once(self):
        guides = G.EditorGuides.__new__(G.EditorGuides)
        guides.root = self.root
        guides._flash = None
        guides._restore_job = None
        guides._cancel = lambda name: None
        guides._begin_flash(self.w)
        during = (str(self.w.cget('insertbackground')), int(self.w.cget('insertwidth')), int(self.w.cget('insertofftime')))
        guides.restore()
        after = (str(self.w.cget('insertbackground')), int(self.w.cget('insertwidth')), int(self.w.cget('insertofftime')))
        return during, after

    def test_light_flash_and_restore(self):
        self.w.configure(background=pane_colors('light')[0])
        during, after = self.flash_once()
        self.assertEqual(during, (G.FLASH_COLOR_LIGHT, 3, 0))
        self.assertEqual(after, ('#222222', 2, 300))

    def test_dark_flash_unchanged(self):
        self.w.configure(background=pane_colors('dark')[0])
        during, after = self.flash_once()
        self.assertEqual(during, (G.FLASH_COLOR, 2, 0))
        self.assertEqual(after, ('#222222', 2, 300))

    def test_theme_switch_picks_by_the_background_now(self):
        self.w.configure(background=pane_colors('sumi')[0])
        self.assertEqual(self.flash_once()[0][0], G.FLASH_COLOR)
        self.w.configure(background=pane_colors('sora')[0])
        self.assertEqual(self.flash_once()[0][0], G.FLASH_COLOR_LIGHT)

    def test_switch_back(self):
        self.w.configure(background='#ffffff')
        with mock.patch.dict(os.environ, {'CN_CARET_FLASH_LIGHT': '0'}):
            during, after = self.flash_once()
        self.assertEqual(during, (G.FLASH_COLOR, 2, 0))                                 # 前の形
        self.assertEqual(after, ('#222222', 2, 300))


if __name__ == '__main__':
    unittest.main()
