# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""外来語の打ち間違い（項目48-IT）: カタカナの語に地続きのかな（ツール|めなゅー）は IME がカタカナ語の続きを
変換しそこねた跡なので、末尾の ー を伸ばし・擬音とは見ず、隣接キー1手で表の語に届けば直す（2026-10-25）。
単独の擬音（うにゅーん・くぅーん）は今までどおり触らない。例文は作ったもの。"""
import unittest

import app as C
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class LoanGluedKatakanaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def _run(self, line):
        return C.correct_line(line, self.store, input_method='kana', dict_index=self.index)

    def test_kana_tail_glued_to_katakana_word_is_repaired_to_the_table_word(self):
        res = self._run('ツールめなゅーを開く')
        self.assertEqual(res['corrected'], 'ツールメニューを開く')

    def test_standalone_onomatopoeia_with_long_vowel_is_left_alone(self):
        for line in ('うにゅーん', 'くぅーんと鳴いた'):
            res = self._run(line)
            self.assertEqual(res['corrected'], line, line)


if __name__ == '__main__':
    unittest.main()
