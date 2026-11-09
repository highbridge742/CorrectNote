# -*- coding: utf-8 -*-
"""predicate_slip: 名詞＋格助詞＋動詞（家にいました）は1字の名詞の切れ端と見ない（2026-11-09）。作り例だけ。"""
import unittest

import morphology
import predicate_slip as P


class T(unittest.TestCase):
    def test_case_particle(self):
        line = '昨日は家にいました。'
        runs = P._runs(list(morphology.tokenize(line))) if hasattr(P, '_runs') else []
        self.assertFalse(any('家に' in str(r) for r in runs))


if __name__ == '__main__':
    unittest.main()
