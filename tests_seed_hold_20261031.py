# -*- coding: utf-8 -*-
"""last_keystroke の展開した費用表（seed_japanese_cost）は、メモリ使用量「低」でも持ち続ける（2026-10-31）。
呼ぶたびに展開すると1回 0.12秒かかり、重い本文20行で 143秒 → 66秒。専有メモリは測って変わらない。"""
import os
import unittest
from unittest.mock import patch

import compact_tables
import last_keystroke


class SeedHoldTests(unittest.TestCase):
    def setUp(self):
        self._saved = last_keystroke._SEED_TABLE
        last_keystroke._SEED_TABLE = None

    def tearDown(self):
        last_keystroke._SEED_TABLE = self._saved

    def test_low_tier_keeps_the_expanded_table(self):
        with patch.dict(os.environ, {compact_tables.ENV: '1'}):
            self.assertTrue(last_keystroke._seed_hold())
            first = last_keystroke._seed_table()
            self.assertIs(last_keystroke._seed_table(), first)

    def test_other_tiers_keep_it_too(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(compact_tables.ENV, None)
            self.assertTrue(last_keystroke._seed_hold())


if __name__ == '__main__':
    unittest.main()
