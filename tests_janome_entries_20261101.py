# -*- coding: utf-8 -*-
"""janome の内蔵辞書の語の控え（janome_import._entry_parts・2026-11-01）。辞書を見渡すたびに20個のモジュール（約190MB）
を読み込んでいた。控えから読んでも、モジュールから読んだときと同じ語が同じ順に出る。"""
import os
import tempfile
import unittest
from unittest.mock import patch

import janome_import
import public_nominal_cache


@unittest.skipUnless(janome_import.HAS_JANOME, 'janome')
class JanomeEntriesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, janome_import.ENTRIES_CACHE_NAME)
        self.patch = patch.object(janome_import, '_entries_cache_path', lambda: self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.folder.cleanup()

    def entries(self):
        return list(janome_import.iter_janome_entries(min_len=1, max_len=1))

    def test_the_cache_gives_the_same_entries(self):
        built = self.entries()                      # モジュールから読んで控えを書く
        self.assertTrue(os.path.exists(self.path))
        with patch.object(janome_import, '_read_part', side_effect=AssertionError('modules read')):
            self.assertEqual(self.entries(), built)
        self.assertGreater(len(built), 1000)

    def test_a_broken_cache_reads_the_modules(self):
        built = self.entries()
        with open(self.path, 'wb') as handle:
            handle.write(b'broken')
        self.assertEqual(self.entries(), built)

    def test_the_bundled_nominal_index_still_accepts_janome_import(self):
        # 同梱の名詞索引は janome_import.py の中身を固定して照合する（固定が外れると索引が黙って外れる）
        self.assertEqual(public_nominal_cache._digest(os.path.abspath(janome_import.__file__)),
                         public_nominal_cache.CODE_SHA256['janome_import'])


if __name__ == '__main__':
    unittest.main()
