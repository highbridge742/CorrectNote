# -*- coding: utf-8 -*-
"""分類語彙表の表（synonyms.load_table）は compact_tables の小さな形で持つ（2026-10-31）。
答えも、words() の並びも、dict で持ったときと同じ。CN_PLAIN_TABLES=1 で dict に戻る。"""
import gzip
import json
import os
import unittest
from unittest.mock import patch

import compact_tables
import synonyms


class CompactStringsTests(unittest.TestCase):
    def test_answers_and_order_like_the_dict(self):
        table = {'b': 'x|y', 'a': '', '': 'empty key', 'あ': '体,1.1,1,1'}
        small = compact_tables.CompactStrings.of(table)
        self.assertEqual(list(small), list(table))
        self.assertEqual(list(small.items()), list(table.items()))
        self.assertEqual(len(small), 4)
        for key in list(table) + ['c', 'ああ', None]:
            self.assertEqual(small.get(key), table.get(key), key)
            self.assertEqual(key in small, key in table, key)
        with self.assertRaises(KeyError):
            small['c']
        self.assertFalse(compact_tables.CompactStrings.of({}))
        with self.assertRaises(ValueError):
            compact_tables.CompactStrings.of({'a\x00': 'b'})


@unittest.skipUnless(os.path.exists(os.path.join(synonyms._HERE, synonyms.TABLE)), 'wlsp_synonyms.json.gz が無い')
class SynonymTableTests(unittest.TestCase):
    def _table(self, plain):
        with gzip.open(os.path.join(synonyms._HERE, synonyms.TABLE), 'rt', encoding='utf-8') as f:
            data = json.load(f)
        env = {compact_tables.PLAIN_TABLES_ENV: '1'} if plain else {}
        with patch.dict(os.environ, env):
            if not plain:
                os.environ.pop(compact_tables.PLAIN_TABLES_ENV, None)
            os.environ.pop(compact_tables.ENV, None)
            return synonyms.Table.from_data(data)

    def test_the_compact_table_answers_like_the_dicts(self):
        plain, small = self._table(True), self._table(False)
        self.assertIsInstance(plain._words, dict)
        self.assertIsInstance(small._words, compact_tables.CompactStrings)
        self.assertEqual([w for w, _ in plain.words()], [w for w, _ in small.words()])
        for word, entries in plain.words():
            self.assertEqual(small.entries(word), entries, word)
            self.assertEqual(small.readings(word), plain.readings(word), word)
        for key in plain._groups:
            self.assertEqual(small.group(key), plain.group(key), key)
        for reading in ('おおきい', 'はし', 'き', 'ない語の読み'):
            self.assertEqual(small.by_reading(reading), plain.by_reading(reading), reading)
        self.assertEqual(small.entries('ない語'), [])


if __name__ == '__main__':
    unittest.main()
