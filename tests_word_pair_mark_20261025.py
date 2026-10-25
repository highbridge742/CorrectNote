# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""語の組の印（word_pair_mark・2026-10-25）: IME が別の語を選んだ型（1語ずつは辞書にある）を、隣の語とつないだ読みで見る。
(A) 漢字の名詞＋漢字の接尾の造語（待ち外→間違い）、(B) 名詞＋格助詞＋かなの動詞（鳥のこさ→取り残さ）。
置いた所は紫。書き方の違い（子ども向け）と正しい組は触らない。例文は作ったもの。"""
import unittest

import app as C
import word_pair_mark
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class WordPairMarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def _run(self, line):
        return C.correct_line(line, self.store, input_method='kana', dict_index=self.index)

    def test_noun_plus_suffix_coinage_becomes_the_joined_word_with_purple(self):
        res = self._run('待ち外の補正をした。')
        self.assertEqual(res['corrected'], '間違いの補正をした。')
        self.assertTrue(any(a <= 0 and b >= 3 for a, b in res['odd_spans']))

    def test_noun_particle_kana_verb_becomes_the_joined_verb_with_purple(self):
        res = self._run('鳥のこされない')
        self.assertEqual(res['corrected'], '取り残されない')
        self.assertTrue(res['odd_spans'])

    def test_spelling_variant_is_not_a_pair(self):
        res = self._run('子ども向けの本を読む。')
        self.assertEqual(res['corrected'], '子ども向けの本を読む。')
        self.assertFalse(res['odd_spans'])

    def test_ordinary_pairs_are_left_alone(self):
        for line in ('駅前の店で昼食を食べた。', '雨の日に傘を持つ。', '会議の資料を机に置く。'):
            res = self._run(line)
            self.assertEqual(res['corrected'], line, line)
            self.assertFalse(res['odd_spans'], line)

    def test_propose_returns_single_candidate_for_coinage(self):
        marks = word_pair_mark.propose('待ち外の補正をした。', self.index)
        self.assertEqual([(s, e, faces) for s, e, faces in marks], [(0, 3, ['間違い'])])

    def test_repair_line_skips_spans_other_repairs_changed(self):
        line = '待ち外の補正をした。'
        result = {'corrected': '待ち外の補正をした。', 'odd_spans': [(0, 3)], 'unsure_spans': []}
        self.assertIs(word_pair_mark.repair_line(line, result, self.store, self.index), result)


if __name__ == '__main__':
    unittest.main()
