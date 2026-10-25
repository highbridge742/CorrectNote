# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""連用形の後ろの尾の1打ずれ（renyou_tail_slip・2026-10-25）: かなの並びが 動詞の連用形＋説明の付かない短い尾
（あそび｜のす）で、尾の1字を隣のキーに替えると助動詞の尾（ます）になるなら直す。候補が1つのときだけ。
正しい文・単独の尾は触らない。例文は作ったもの。"""
import unittest

import app as C
import renyou_tail_slip
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class RenyouTailSlipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def _run(self, line):
        return C.correct_line(line, self.store, input_method='kana', dict_index=self.index)

    def test_slipped_polite_tail_after_renyou_verb_is_repaired(self):
        res = self._run('友だちとあそびのす')
        self.assertEqual(res['corrected'], '友だちと遊びます')
        self.assertFalse(res['odd_spans'])

    def test_propose_finds_the_single_candidate(self):
        cands = [c for _, _, c in renyou_tail_slip.propose('ケーキをつくりのす')]
        self.assertEqual(len(cands), 1)
        self.assertTrue(cands[0].endswith('つくります'), cands)

    def test_correct_polite_and_plain_sentences_are_left_alone(self):
        for line in ('友だちと遊びます。', '本を読みました。', 'ケーキをつくります', '駅まであるきたい'):
            self.assertEqual(renyou_tail_slip.propose(line), [], line)

    def test_particle_tail_is_not_treated_as_auxiliary(self):
        # つくり＋のか は「助詞の尾」。助動詞の尾（ます）に替える候補とは別の形なので候補に数えない
        self.assertNotIn('つくりのか', [c for _, _, c in renyou_tail_slip.propose('ケーキをつくりのす')])


if __name__ == '__main__':
    unittest.main()
