# -*- coding: utf-8 -*-
"""デバッグメニューの窓の高さと最小化ボタン（2026-11-23 うにさん「デバッグメニューの上にボタンが入った分、パラメータが縦に
狭いので、ウインドウを縦に広げて。最小化ボタンも付ける」）。
・既定の高さは 880（前は 620）。作業領域の高さから枠を引いた所で上限・前の既定より小さくはしない（作業領域が狭い時を除く）
・transient にしない（Windows では transient の窓に最小化ボタンが出ない）
CN_DEBUG_WINDOW_TALLER=0 で前の形（620・transient）。画面の外に置く。"""
import os
import tempfile
import time
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import debug_menu
from settings import Settings


class DebugWindowSize(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = tk.Tk(); __import__('offscreen_window').hold(self.root, '200x100')
        self.addCleanup(self.root.destroy)
        self.a = object.__new__(app.CorrectNoteApp)
        self.a.settings = Settings(os.path.join(self.dir.name, 'settings.json'))
        self.a.root = self.root
        self.sizes = []
        def place(dlg, w, h):
            self.sizes.append((w, h))
            __import__('offscreen_window').hold(dlg, '%dx%d' % (w, h))
        self.a._place_dialog = place
        self.addCleanup(debug_menu.apply, object.__new__(app.CorrectNoteApp), {})

    def open(self):
        dlg = self.a.open_debug_menu()
        for _ in range(10):
            self.root.update(); time.sleep(0.01)
        transient = str(dlg.tk.call('wm', 'transient', dlg._w))
        dlg.destroy()
        self.a._debug_window = None
        return self.sizes[-1], transient

    def test_taller_and_minimizable(self):
        (w, h), transient = self.open()
        self.assertEqual(w, 640)
        self.assertEqual(h, debug_menu.window_height(self.a))
        self.assertGreater(h, debug_menu.OLD_HEIGHT)          # この机の作業領域なら前より高い
        self.assertEqual(transient, '')                        # transient でない＝最小化ボタンが出る

    def test_capped_by_the_work_area(self):
        with mock.patch.object(app, 'monitor_work_area', lambda x, y: (0, 0, 1280, 700)), \
                mock.patch.object(app, 'window_frame_size', lambda root: (16, 39)):
            self.assertEqual(debug_menu.window_height(self.a), 661)       # 700 − 39
        with mock.patch.object(app, 'monitor_work_area', lambda x, y: (0, 0, 1920, 1400)), \
                mock.patch.object(app, 'window_frame_size', lambda root: (16, 39)):
            self.assertEqual(debug_menu.window_height(self.a), debug_menu.WINDOW_HEIGHT)
        with mock.patch.object(app, 'monitor_work_area', lambda x, y: (0, 0, 1280, 500)), \
                mock.patch.object(app, 'window_frame_size', lambda root: (16, 39)):
            self.assertEqual(debug_menu.window_height(self.a), 461)       # 前の既定より狭い作業領域でも収める

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_DEBUG_WINDOW_TALLER': '0'}):
            (w, h), transient = self.open()
        self.assertEqual((w, h), (640, debug_menu.OLD_HEIGHT))
        self.assertNotEqual(transient, '')                     # 前の形: transient（最小化ボタン無し）


if __name__ == '__main__':
    unittest.main()
