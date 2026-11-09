# -*- coding: utf-8 -*-
"""入口の直しが行頭の接尾の崩れを解析の読みから別の語に直した所を戻して紫にする（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import ime_reconvert as R


class _Rev:
    available = True

    def __init__(self, table):
        self.table = table

    def reverse_words(self, text):
        return self.table.get(text)


TABLE = {'的背を見る': ('まとせをみる', ((0, 1, 0, 2, 0, 0), (1, 2, 2, 3, 0, 0), (2, 3, 3, 4, 0, 0), (3, 5, 4, 6, 0, 0)))}


class UndoHead(unittest.TestCase):
    def setUp(self):
        R._IME_REVERSE.clear()
        R._remember_ime_reverse('的背を見る', _Rev(TABLE))
        self.res = {'original': '的背を見る', 'corrected': '敵背を見る', 'changed': True,
                    'details': [['的', '敵', 'かな入力']], 'odd_spans': [], 'odd_reasons': []}

    def test_undo(self):
        out = R._undo_broken_head_fix('的背を見る', self.res)
        self.assertEqual(out['corrected'], '的背を見る')
        self.assertIn((0, 2), [tuple(x[:2]) for x in out['odd_spans']])

    def test_no_ime_reading(self):
        R._IME_REVERSE.clear()
        self.assertIs(R._undo_broken_head_fix('的背を見る', self.res), self.res)

    def test_switch(self):
        os.environ['CN_RECONVERT_UNDO_HEAD'] = '0'
        try:
            self.assertIs(R._undo_broken_head_fix('的背を見る', self.res), self.res)
        finally:
            del os.environ['CN_RECONVERT_UNDO_HEAD']


if __name__ == '__main__':
    unittest.main()
