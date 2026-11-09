# -*- coding: utf-8 -*-
"""2026-11-05 うに「weaoin が weapon に補正されない。p キーが隣接ミスしたことで、後続キーも流れで隣を押すケース」
「基準キーのズレ」: 続く2つ以上のキーが同じ段で同じ向きに1つずれた打ち違いを戻す。例は作った語。"""
import os
import unittest

import en_typo as T


class ShiftRunTests(unittest.TestCase):
    def test_fixed(self):
        for typed, want in (('weaoin', 'weapon'), ('hekko', 'hello'), ('mpther', 'mother')):
            self.assertEqual(T.best_word(typed), want, typed)

    def test_short_or_whole_word_left(self):
        # 4字以下・語の頭からのずれ・語の半分を超えるずれは見ない
        for typed in ('lomd', 'dir', 'abs', 'sdk'):
            self.assertNotEqual(T.one_slip(typed).get(T.best_word(typed) or '', ''), 'shift', typed)

    def test_switch(self):
        os.environ['CN_EN_SHIFT_RUN'] = '0'
        try:
            self.assertEqual(T._shifted_runs('weaoin'), [])
        finally:
            del os.environ['CN_EN_SHIFT_RUN']


if __name__ == '__main__':
    unittest.main()
