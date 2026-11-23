# -*- coding: utf-8 -*-
"""オンマウスで候補を出すのは入力カーソルの近くに限定（2026-11-23 01:21 JST うにさん「オプションに、『オンマウスで候補を
出すのは入力カーソルの近くに限定』を追加。デフォルトはオフ。デバッグメニューに、この近くが上下何行かのパラメータを出す。
デフォルトを10。上限は100」）。オフで今どおり／オンで範囲の外は出さない・中は出す／行数の上限・下限。
CN_HOVER_NEAR_CURSOR=0 で設定に関係なく前の形。Tk の窓は出さない（作った字だけ）。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC
import debug_menu
import settings as S


class Settings(dict):
    def set(self, k, v):
        self[k] = v

    def save(self):
        pass


class NearCursor(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root, height=60, font=('Meiryo', 9))
        self.w.insert('1.0', '\n'.join('%d行目の作った文です。' % i for i in range(1, 80)))
        self.w.pack()
        self.root.update()
        self.w.mark_set('insert', '30.0')
        self.app = NS(editor=self.w, settings=Settings())

    def at_row(self, row):
        self.w.see('%d.0' % row)
        self.root.update()
        d = self.w.dlineinfo('%d.0' % row)
        return NS(x=d[0] + 5, y=d[1] + d[3] // 2)

    def test_off_is_as_before(self):
        self.assertFalse(S.DEFAULTS['hover_near_cursor'])                      # 既定オフ
        self.app.settings['hover_near_cursor'] = False
        self.assertTrue(AC.near_cursor(self.app, self.w, self.at_row(70)))   # 遠くても出す（今どおり）

    def test_on_limits_to_rows_near_the_cursor(self):
        self.app.settings['hover_near_cursor'] = True
        self.assertEqual(AC.HOVER_NEAR_ROWS, 10)
        self.assertTrue(AC.near_cursor(self.app, self.w, self.at_row(40)))    # 上下10行の中（30→40）
        self.assertTrue(AC.near_cursor(self.app, self.w, self.at_row(20)))
        self.assertFalse(AC.near_cursor(self.app, self.w, self.at_row(41)))   # 11行離れた
        self.assertFalse(AC.near_cursor(self.app, self.w, self.at_row(19)))
        with mock.patch.object(AC, 'HOVER_NEAR_ROWS', 0):
            self.assertTrue(AC.near_cursor(self.app, self.w, self.at_row(30)))   # 0: カーソルの行だけ
            self.assertFalse(AC.near_cursor(self.app, self.w, self.at_row(31)))
        # _hit も同じ所で止まる（語を探す前に）
        self.assertIsNone(AC._hit(self.app, self.w, self.at_row(60)))
        with mock.patch.dict(os.environ, {'CN_HOVER_NEAR_CURSOR': '0'}):
            self.assertTrue(AC.near_cursor(self.app, self.w, self.at_row(60)))   # 前の形

    def test_debug_menu_rows(self):
        self.assertEqual(debug_menu.default('hover_near_rows'), 10)
        self.assertEqual(debug_menu.minimum('hover_near_rows'), 0)
        self.assertEqual(debug_menu.maximum('hover_near_rows'), 100)
        self.assertEqual(debug_menu.clamp('hover_near_rows', 500), 100)       # 上限で丸める
        self.assertEqual(debug_menu.clamp('hover_near_rows', -3), 0)
        self.assertEqual(debug_menu.parse('hover_near_rows', 'x'), None)
        app = NS(settings=Settings(debug_timings={}))
        try:
            debug_menu.set_value(app, 'hover_near_rows', 25, save=False)
            self.assertEqual(AC.HOVER_NEAR_ROWS, 25)                          # その場で効く
            self.assertEqual(app.settings['debug_timings'], {'hover_near_rows': 25})
        finally:
            debug_menu.set_value(app, 'hover_near_rows', 10, save=False)
        self.assertEqual(AC.HOVER_NEAR_ROWS, 10)
        self.assertEqual(app.settings['debug_timings'], {})                  # 既定は保存しない

    def test_english_labels(self):
        import ui_lang_en
        text = open(ui_lang_en.__file__, encoding='utf-8').read()
        self.assertIn('Show hover candidates only near the text cursor', text)


if __name__ == '__main__':
    unittest.main()
