# -*- coding: utf-8 -*-
"""wago_verb: くだけた言い方（格子の読みが フィラー・動詞＋1字の動詞）では動詞を置かない（2026-11-09 batch440）。"""
import unittest

import wago_verb as W


def run(line):
    return W.repair_line(line, {'corrected': line, 'changed': False}).get('corrected')


class T(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(run('うめえなあ'), 'うめえなあ')

    def test_still(self):
        self.assertEqual(run('てがみをうちました'), 'てがみを打ちました')


if __name__ == '__main__':
    unittest.main()
