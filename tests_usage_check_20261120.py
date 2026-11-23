# -*- coding: utf-8 -*-
"""デバッグメニュー「補正の段の使われ方を数える」のチェックとリセット（2026-11-20 うにさん「他の記録の項目と同じ形の
チェックボックスを付ける（既定オフ。オフの間は数えない＝処理を軽く。設定に保存）。その窓の中にリセットボタン」）。
作った値と一時のファイルだけ。"""
import os
import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import analysis_worker
import debug_menu
import settings
import usage_counts


class FakeSettings(dict):
    def set(self, key, value):
        self[key] = value

    def save(self):
        self.saved = True


class UsageCheck(unittest.TestCase):
    def setUp(self):
        self._was = usage_counts.ON
        self.addCleanup(setattr, usage_counts, 'ON', self._was)
        self._counts = dict(usage_counts.COUNTS)
        self.addCleanup(lambda: (usage_counts.COUNTS.clear(), usage_counts.COUNTS.update(self._counts)))

    def test_default_off_and_request_flag(self):
        self.assertIs(settings.DEFAULTS['debug_usage_counts'], False)
        usage_counts.ON = False
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CN_USAGE_COUNTS_ALWAYS', None)
            self.assertFalse(analysis_worker.usage_setting())
            usage_counts.ON = True
            self.assertTrue(analysis_worker.usage_setting())
        usage_counts.ON = False
        with mock.patch.dict(os.environ, {'CN_USAGE_COUNTS_ALWAYS': '1'}):
            self.assertTrue(analysis_worker.usage_setting())               # 前の形（いつも数える）

    def test_check_saves_the_setting(self):
        app = NS(settings=FakeSettings())
        debug_menu.choose_usage_counts(app, True)
        self.assertIs(app.settings['debug_usage_counts'], True)
        self.assertTrue(usage_counts.ON)
        debug_menu.choose_usage_counts(app, False)
        self.assertFalse(usage_counts.ON)

    def test_reset_clears_counts_and_the_file(self):
        usage_counts.COUNTS['x.stage'] = [3, 2, 1]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'usage_counts.json')
            open(path, 'w').write('{}')
            import app as app_module
            with mock.patch.object(app_module, 'USAGE_COUNTS_FILE', path):
                debug_menu.reset_usage_counts(NS(_usage_saved={'a': 1}))
            self.assertFalse(os.path.exists(path))
        self.assertEqual(usage_counts.COUNTS, {})

    def test_window_has_a_reset_button(self):
        root = tk.Tk()
        root.withdraw()
        try:
            dlg = debug_menu.open_usage_window(NS(root=root))
            self.assertIn('リセット', dlg._usage_reset.cget('text'))
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
