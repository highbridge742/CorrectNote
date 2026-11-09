# -*- coding: utf-8 -*-
"""honorific_stem: お＋動詞＋する で直した所の前の紫を外す（2026-11-09）。作り例だけ。"""
import os
import unittest

import honorific_stem as H


class T(unittest.TestCase):
    def test_clears(self):
        line = '来週お餅します'
        r = H.repair_line(line, {'corrected': line, 'changed': False, 'odd_spans': [(2, 4)], 'odd_reasons': [(2, 4, 'x')]})
        self.assertEqual(r['corrected'], '来週お持ちします')
        self.assertEqual(list(r['odd_spans']), [])

    def test_switch(self):
        os.environ['CN_HONORIFIC_CLEARS_ODD'] = '0'
        try:
            line = '来週お餅します'
            r = H.repair_line(line, {'corrected': line, 'changed': False, 'odd_spans': [(2, 4)]})
            self.assertEqual([tuple(x) for x in r['odd_spans']], [(2, 4)])
        finally:
            del os.environ['CN_HONORIFIC_CLEARS_ODD']


if __name__ == '__main__':
    unittest.main()
