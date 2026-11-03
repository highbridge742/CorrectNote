# -*- coding: utf-8 -*-
"""類語の表の詰めた形の控え（synonyms._load_compact・2026-11-01）。解析の子の起動ごとに表の JSON を読んで詰め直すのに
1.3秒かかっていた（控えからは 0.1秒）。控えから作った表は、表のファイルから作った表と同じ答えを返す。"""
import os
import tempfile
import unittest
from unittest.mock import patch

import synonyms


class SynonymsCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.folder.name, synonyms.COMPACT_CACHE)
        self.patch = patch.object(synonyms, '_compact_cache_path', lambda: self.cache)
        self.patch.start()
        synonyms.load_table.cache_clear()

    def tearDown(self):
        self.patch.stop()
        synonyms.load_table.cache_clear()
        self.folder.cleanup()

    def signature(self, table):
        words = list(table.words())
        return (words, [table.group(k) for k in list(table._groups)[:500]],
                [table.readings(w) for w, _ in words[:500]], [table.by_reading(r) for r in ('おおきい', 'かいぎ')])

    def test_the_cached_table_answers_the_same(self):
        built = synonyms.load_table()
        if not built:
            self.skipTest('no synonyms table')
        self.assertTrue(os.path.exists(self.cache))
        synonyms.load_table.cache_clear()
        cached = synonyms._load_compact(os.path.join(synonyms._HERE, synonyms.TABLE))
        self.assertIsNotNone(cached)
        self.assertEqual(self.signature(cached), self.signature(built))

    def test_a_changed_table_file_is_read_again(self):
        if not synonyms.load_table():
            self.skipTest('no synonyms table')
        with patch.object(synonyms, '_table_stamp', lambda path: ('another table',)):
            self.assertIsNone(synonyms._load_compact(os.path.join(synonyms._HERE, synonyms.TABLE)))


if __name__ == '__main__':
    unittest.main()
