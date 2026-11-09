# -*- coding: utf-8 -*-
"""predicate_slip._runs: 漢字の動詞の連用形＋かなの動詞が自立に切れた形（取れ｜かかる｜。）と、助詞の後ろの
1字の漢字の名詞＋1字の助詞＋動詞（に｜都｜の｜掛かる）も述語の並びとして見る（2026-11-09 手分けB）。例は作った文。"""
import os
import unittest

import predicate_slip as P
from morphology import tokenize


def _runs(s):
    return [r[2] for r in P._runs(list(tokenize(s)))]


class SplitVerbRuns(unittest.TestCase):
    def test_tail_verb(self):
        self.assertIn('取れかかる', _runs('作業に取れかかる。'))

    def test_kanji_piece(self):
        self.assertIn('都の掛かる', _runs('宿題に都の掛かる。'))

    def test_not_after_noun_start(self):
        # 行頭の 1字の名詞＋の＋動詞 は見ない（前に助詞が要る）
        self.assertEqual(_runs('都の掛かる。'), [])

    def test_switches(self):
        os.environ['CN_PS_TAIL_VERB'] = '0'
        os.environ['CN_PS_KANJI_PIECE'] = '0'
        try:
            self.assertEqual(_runs('作業に取れかかる。'), [])
            self.assertEqual(_runs('宿題に都の掛かる。'), [])
        finally:
            del os.environ['CN_PS_TAIL_VERB']
            del os.environ['CN_PS_KANJI_PIECE']


if __name__ == '__main__':
    unittest.main()
