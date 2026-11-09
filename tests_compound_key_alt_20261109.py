# -*- coding: utf-8 -*-
"""compound_key_alt（漢字の名詞の組を読みに戻して1打違いの置き直しに掛ける・2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import compound_key_alt as C


class CompoundKeyAlt(unittest.TestCase):
    def test_fix(self):
        self.assertEqual(C.propose('野外列車'), [(0, 4, '長い列車')])

    def test_correct_compounds_kept(self):
        for t in ('屋外照明', '会議資料を読む', '感想欄に一言どうぞ。', '長い列車'):
            self.assertEqual(C.propose(t), [], t)

    def test_switch(self):
        os.environ['CN_COMPOUND_KEY_ALT'] = '0'
        try:
            self.assertEqual(C.propose('野外列車'), [])
        finally:
            del os.environ['CN_COMPOUND_KEY_ALT']


if __name__ == '__main__':
    unittest.main()
