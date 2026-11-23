# -*- coding: utf-8 -*-
"""語彙の見分け（analysis_cache._vocab_stamp）を、同じ語彙なら覚えておく（2026-11-20 うにさん「文字を打って確定して
から、本文に文字が反映されるまでも重い」: 打鍵のあとの段取りで、控えの指紋のために全語を毎回数え直していた）。
覚えた値と数え直した値が同じこと・語彙が変われば数え直すこと・切り替えで前の形。作った語だけ。"""
import os
import unittest
from unittest import mock

import analysis_cache as AC
from vocabulary import VocabularyStore


def store_with(words):
    s = VocabularyStore()
    for reading, surface in words:
        s.add(reading, surface)
    return s


class VocabStampMemo(unittest.TestCase):
    def setUp(self):
        AC._VOCAB_STAMP_MEMO.clear()

    def fresh(self, store):
        with mock.patch.dict(os.environ, {'CN_VOCAB_STAMP_MEMO': '0'}):
            return AC._vocab_stamp(store)

    def test_memo_matches_a_fresh_count_and_follows_changes(self):
        s = store_with([('あめ', '雨'), ('かさ', '傘')])
        first = AC._vocab_stamp(s)
        self.assertEqual(first, self.fresh(s))
        with mock.patch.object(s, 'to_list', side_effect=AssertionError('counted again')):
            self.assertEqual(AC._vocab_stamp(s), first)             # 同じ revision: 数え直さない
        s.add('ほん', '本')
        second = AC._vocab_stamp(s)
        self.assertNotEqual(second, first)                          # 語彙が変われば数え直す
        self.assertEqual(second, self.fresh(s))

    def test_another_store_is_counted(self):
        a = store_with([('あめ', '雨')])
        b = store_with([('かさ', '傘')])
        self.assertEqual(AC._vocab_stamp(a), self.fresh(a))
        self.assertEqual(AC._vocab_stamp(b), self.fresh(b))

    def test_switch_back_counts_every_time(self):
        s = store_with([('あめ', '雨')])
        AC._vocab_stamp(s)
        with mock.patch.dict(os.environ, {'CN_VOCAB_STAMP_MEMO': '0'}), \
                mock.patch.object(s, 'to_list', wraps=s.to_list) as counted:
            AC._vocab_stamp(s)
        counted.assert_called_once()


if __name__ == '__main__':
    unittest.main()
