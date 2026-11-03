# -*- coding: utf-8 -*-
"""サ変の名詞に動詞が直に付いた形（名詞＋居て・名詞＋し＋別の動詞）を述語の打ち違いとして見る（predicate_slip・2026-11-01 B）。作った例だけ。"""
import unittest
import morphology
import predicate_slip as P


def kinds(text):
    return [(form, kind) for _i, _j, form, kind in P._runs(list(morphology.tokenize(text)))]


class SahenRunTests(unittest.TestCase):
    def test_noun_then_verb(self):
        self.assertIn(('掃除居る', 'sahen'), kinds('部屋を掃除居て休む'))

    def test_noun_shi_then_verb(self):
        self.assertIn(('掃除し舞う', 'sahen'), kinds('部屋を掃除し舞う'))

    def test_plain_suru_is_not_a_run(self):
        self.assertFalse([k for k in kinds('部屋を掃除して休む') if k[1] == 'sahen'])

    def test_tails_are_suru_endings_only(self):
        self.assertIn('ます', P.SAHEN_TAILS)
        self.assertNotIn('いて', P.SAHEN_TAILS)


if __name__ == '__main__':
    unittest.main()
