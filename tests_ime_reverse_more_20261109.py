# -*- coding: utf-8 -*-
"""IME の逆変換の読みの使い道を広げる（2026-11-09 手分けA）。例は作った文。
LineReading は odd_respell.py.diff、OneKeyFix は correction_entry.py.diff を入れたときだけ通る。"""
import os
import unittest

import ime_reconvert as R
from morphology import tokenize


class _Rev:
    available = True

    def __init__(self, rw):
        self.rw = rw

    def reverse_words(self, text):
        return self.rw


class HeadSuffix(unittest.TestCase):
    def test_head_suffix_marked(self):
        t = '的背を見る'
        self.assertEqual(R._head_suffix_marks(t, list(tokenize(t))), [(0, 2, None)])

    def test_normal_suffix_kept(self):
        for t in ('経済的な話', '会議室に集まる', '安全性を高める'):
            self.assertEqual(R._head_suffix_marks(t, list(tokenize(t))), [], t)

    def test_switch(self):
        os.environ['CN_RECONVERT_HEAD_SUFFIX'] = '0'
        try:
            t = '的背を見る'
            self.assertEqual(R._head_suffix_marks(t, list(tokenize(t))), [])
        finally:
            del os.environ['CN_RECONVERT_HEAD_SUFFIX']


class LineReading(unittest.TestCase):
    def test_uses_ime(self):
        import odd_respell as O
        R._IME_REVERSE.clear()
        R._remember_ime_reverse('的買い', _Rev(('まとがい', ((0, 1, 0, 2, 0, 0), (1, 3, 2, 4, 0, 0)))))
        self.assertEqual(O._line_reading('的買い'), 'まとがい')
        R._IME_REVERSE.clear()
        self.assertNotEqual(O._line_reading('的買い'), 'まとがい')


class OneKeyFix(unittest.TestCase):
    def test_one_key(self):
        import correction_entry as CE
        line = '乳リュク見る'
        R._IME_REVERSE.clear()
        R._remember_ime_reverse(line, _Rev(('にゅうりゅくみる', ((0, 1, 0, 3, 0, 0), (1, 4, 3, 6, 0, 0), (4, 6, 6, 8, 0, 0)))))
        self.assertTrue(CE._ime_one_key_fix(line, 0, 4, '入力'))
        self.assertFalse(CE._ime_one_key_fix(line, 0, 4, '乳'))
        R._IME_REVERSE.clear()
        self.assertFalse(CE._ime_one_key_fix(line, 0, 4, '入力'))


if __name__ == '__main__':
    unittest.main()
