# -*- coding: utf-8 -*-
"""英語の説明書（2026-11-23 うにさん「英語で起動するか、英語で説明書を押すまで、英語のHTMLは出力しないでください」）。
・日本語で起動: 英語の説明書は書き出さない（日本語の説明書は今どおり）
・英語で起動: 英語の説明書を書き出す
・途中で英語へ替えても、説明書を押すまでは書き出さない。英語の画面で押すと英語の説明書を書き出して開く。日本語の画面で
  押すと日本語の説明書
CN_MANUAL_EN=0 で前の形（いつも日本語だけ）。一時フォルダと作った字だけ（同梱の実物・本物の説明書は読まない）。
窓は出さない（ブラウザで開く所は差し替える）。"""
import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import ui_lang


class FakeSettings(dict):
    def set(self, k, v):
        self[k] = v

    def save(self):
        pass


class ManualEn(unittest.TestCase):
    def setUp(self):
        base = tempfile.mkdtemp(prefix='cn-manual-')
        self.bundle = os.path.join(base, 'bundle')
        self.out = os.path.join(base, 'out')
        os.makedirs(self.bundle)
        os.makedirs(self.out)
        for name in (app.MANUAL_FILENAME, app.MANUAL_EN_FILENAME):
            with open(os.path.join(self.bundle, name), 'w', encoding='utf-8') as f:
                f.write('<html>%s</html>' % name)
        bundled = lambda name: (os.path.join(self.bundle, name)
                                if os.path.exists(os.path.join(self.bundle, name)) else None)
        self.patches = [mock.patch.object(app, 'bundled_path', bundled),
                        mock.patch.object(app, 'MANUAL_FILE', os.path.join(self.out, app.MANUAL_FILENAME)),
                        mock.patch.object(app, 'MANUAL_EN_FILE', os.path.join(self.out, app.MANUAL_EN_FILENAME)),
                        mock.patch.object(app, 'app_dir', lambda: self.out)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.opened = []
        p = mock.patch.object(app.os, 'startfile', lambda path: self.opened.append(os.path.basename(path)), create=True)
        p.start()
        self.addCleanup(p.stop)
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.settings = FakeSettings()
        self.a.status = NS(config=lambda **k: None)

    def exists(self, name):
        return os.path.exists(os.path.join(self.out, name))

    def lang(self, english):
        return mock.patch.object(ui_lang, 'is_japanese', lambda: not english)

    def test_japanese_start_does_not_write_english(self):
        with self.lang(False):
            self.a._extract_manual_on_start()
        self.assertTrue(self.exists(app.MANUAL_FILENAME))            # 日本語は今どおり
        self.assertFalse(self.exists(app.MANUAL_EN_FILENAME))

    def test_english_start_writes_english(self):
        with self.lang(True):
            self.a._extract_manual_on_start()
        self.assertTrue(self.exists(app.MANUAL_EN_FILENAME))

    def test_switched_to_english_writes_only_when_pressed(self):
        with self.lang(False):
            self.a._extract_manual_on_start()
        with self.lang(True):                                        # 途中で英語へ
            self.assertFalse(self.exists(app.MANUAL_EN_FILENAME))    # 押すまでは書き出さない
            self.a.open_manual()
        self.assertTrue(self.exists(app.MANUAL_EN_FILENAME))
        self.assertEqual(self.opened, [app.MANUAL_EN_FILENAME])

    def test_japanese_press_opens_japanese(self):
        with self.lang(False):
            self.a.open_manual()
        self.assertEqual(self.opened, [app.MANUAL_FILENAME])
        self.assertFalse(self.exists(app.MANUAL_EN_FILENAME))

    def test_english_missing_falls_back_to_japanese(self):
        os.remove(os.path.join(self.bundle, app.MANUAL_EN_FILENAME))
        with self.lang(True):
            self.a.open_manual()
        self.assertEqual(self.opened, [app.MANUAL_FILENAME])

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_MANUAL_EN': '0'}), self.lang(True):
            self.a._extract_manual_on_start()
            self.a.open_manual()
        self.assertFalse(self.exists(app.MANUAL_EN_FILENAME))
        self.assertEqual(self.opened, [app.MANUAL_FILENAME])

    def test_bundle_manifest_lists_it(self):
        import bundle_manifest
        self.assertIn(app.MANUAL_EN_FILENAME, [i.name for i in bundle_manifest.ITEMS])


if __name__ == '__main__':
    unittest.main()
