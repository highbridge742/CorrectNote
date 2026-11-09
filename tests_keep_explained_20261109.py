# -*- coding: utf-8 -*-
"""odd_respell が、入口の直しを戻した所（_explained_kana_revert）を紫の読み直しでまた同じ直しにしない（2026-11-09 手分けA）。
odd_respell.py.diff を入れたときだけ通る。例は作った文。"""
import os
import unittest

import odd_respell as O


class KeepExplained(unittest.TestCase):
    def setUp(self):
        self.line = 'もじのほせいをする'
        self.res = {'original': self.line, 'corrected': self.line, 'odd_spans': [[2, 3]],
                    '_explained_rejected': 'もじりほせいをする'}
        self.out = dict(self.res, corrected='もじりほせいをする', odd_spans=[])

    def test_keep(self):
        self.assertIs(O._homophone_guard(self.res, self.out, self.line), self.res)

    def test_switch(self):
        os.environ['CN_RESPELL_KEEP_EXPLAINED'] = '0'
        try:
            got = O._homophone_guard(self.res, self.out, self.line)
            self.assertEqual(got['corrected'], 'もじりほせいをする')
        finally:
            del os.environ['CN_RESPELL_KEEP_EXPLAINED']


if __name__ == '__main__':
    unittest.main()
