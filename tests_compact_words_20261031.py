# -*- coding: utf-8 -*-
"""語の表（seed_japanese・oddness の 77万語）は、2026-10-31 からどの段でも詰めた形（compact_tables）で持つ
（子1つで約120MB少ない）。答えは同じ: 同じ語が在り、無い語は無い。CN_PLAIN_WORDS=1 で従来の set に戻る。"""
import os
import random
import unittest
from unittest.mock import patch

import compact_tables
import word_table


SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seed_japanese.txt.gz')


class CompactWordsTests(unittest.TestCase):
    def test_every_tier_uses_the_compact_words_unless_told_otherwise(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(compact_tables.ENV, None)
            os.environ.pop(compact_tables.PLAIN_WORDS_ENV, None)
            self.assertTrue(compact_tables.words_compact())
            os.environ[compact_tables.PLAIN_WORDS_ENV] = '1'
            self.assertFalse(compact_tables.words_compact())
            os.environ[compact_tables.ENV] = '1'                   # low: compact anyway
            self.assertTrue(compact_tables.words_compact())

    @unittest.skipUnless(os.path.exists(SEED), 'seed_japanese.txt.gz が無い')
    def test_the_compact_words_answer_like_the_sets(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(compact_tables.ENV, None)
            os.environ[compact_tables.PLAIN_WORDS_ENV] = '1'
            word_table._cached.cache_clear()
            plain_wide, plain_narrow = word_table.read_word_sets(SEED)
            os.environ.pop(compact_tables.PLAIN_WORDS_ENV, None)
            word_table._compact_cached.cache_clear()
            wide, narrow = word_table.read_word_sets(SEED)
        self.assertNotIsInstance(wide, (set, frozenset))
        self.assertEqual(len(wide), len(plain_wide))
        self.assertEqual(len(narrow), len(plain_narrow))
        rnd = random.Random(31)
        sample = rnd.sample(sorted(plain_wide), 2000)
        self.assertTrue(all(word in wide for word in sample))
        narrow_sample = rnd.sample(sorted(plain_narrow), min(2000, len(plain_narrow)))
        self.assertTrue(all(word in narrow for word in narrow_sample))
        for word in ('あいうえおかきくけこ', '存在しない語の並び', 'ｱｲｳ', ''):
            self.assertEqual(word in wide, word in plain_wide, word)
            self.assertEqual(word in narrow, word in plain_narrow, word)

    def test_the_bundled_nominal_index_still_accepts_word_table(self):
        # 同梱の名詞索引（public_nominal_cache）は word_table.py の中身を固定して照合する。
        # 2026-10-31: 詰めた形へ変えたとき固定を直し忘れ、索引が外れて tests_mock の
        # 「ひきつぎしりょうは正しい読みを保つ」が NG になった（答えは同じなので固定だけ直す）
        import public_nominal_cache
        path = os.path.abspath(word_table.__file__)
        self.assertEqual(public_nominal_cache._digest(path), public_nominal_cache.CODE_SHA256['word_table'])


if __name__ == '__main__':
    unittest.main()
