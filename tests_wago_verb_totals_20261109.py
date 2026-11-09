# -*- coding: utf-8 -*-
"""wago_verb の続き（2026-11-09 batch434）: 例文の組の数の足し合わせ・後ろが動詞にしか付かない語・名詞＋で・名詞＋連用形の名詞化（かな打ち）。"""
import unittest

import wago_verb as W


def run(line):
    return W.repair_line(line, {'corrected': line, 'changed': False}).get('corrected')


class T(unittest.TestCase):
    def test_totals(self):
        self.assertEqual(W.choose('うち'), '打ち')

    def test_verb_only_next(self):
        self.assertEqual(run('てがみをうちました'), 'てがみを打ちました')

    def test_noun_de_case(self):
        self.assertEqual(run('こうえんであそんだ'), 'こうえんで遊んだ')

    def test_noun_renyou(self):
        self.assertEqual(W._noun_renyou('かなうちでの'), (2, 4, '打ち'))
        for l in ('ぜんぶうちでやった', 'みんなうちにきた', 'くにのうちでも'):
            self.assertEqual(run(l), l)

    def test_keep(self):
        for l in ('いただきます', 'うちのねこはかわいい', 'いってきます'):
            self.assertEqual(run(l), l)


if __name__ == '__main__':
    unittest.main()
