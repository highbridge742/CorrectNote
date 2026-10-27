# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""機能語だけの単位（ます・ました・たい・ください）に、再変換の「打ち間違いの可能性」を出さない（2026-10-25）。
助動詞 ます の単位が functional でなかったので 48-GL の門を通らず、意味の通らない打ち間違い候補が並んだ。
1字の助詞と同じ門を、それだけで機能語の並びになる単位にも掛ける。例文は作ったもの。"""
import unittest

import app as C
import corrector
import units
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class FunctionalUnitCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()
        cls.fn = staticmethod(corrector.make_tokenizer(cls.store))

    def _units(self, line):
        res = C.correct_line(line, self.store, input_method='kana', dict_index=self.index)
        _text, us = units.build_line_units(res, self.fn, None, None)
        return {u.get('text'): bool(u.get('functional')) for u in us}

    def test_polite_auxiliary_unit_is_functional(self):
        got = self._units('ケーキをつくります')
        self.assertTrue(got.get('ます'))
        self.assertTrue(got.get('を'))
        self.assertFalse(got.get('つくり'))
        self.assertFalse(got.get('ケーキ'))

    def test_other_auxiliary_tails_are_functional(self):
        self.assertTrue(self._units('みかんをたべたい').get('たい'))
        self.assertTrue(self._units('かみをよんでください').get('ください'))

    def test_content_kana_unit_stays_open_to_candidates(self):
        got = self._units('りんごをかいます')
        self.assertFalse(got.get('りんご'))
        self.assertTrue(got.get('ます'))

    def test_auto_fixed_auxiliary_unit_is_functional(self):
        # 直された側（のす→ます・kind='fixed'）にも同じ印が付く
        got = self._units('ケーキをつくりのす')
        self.assertTrue(got.get('ます'))
        self.assertFalse(got.get('つくり'))

    def test_all_functional_helper(self):
        self.assertTrue(corrector._is_all_functional('ます'))
        self.assertTrue(corrector._is_all_functional('ました'))
        self.assertFalse(corrector._is_all_functional('つくり'))
        self.assertFalse(corrector._is_all_functional('のす'))


if __name__ == '__main__':
    unittest.main()
