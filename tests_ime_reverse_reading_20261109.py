# -*- coding: utf-8 -*-
"""IME の逆変換の読みを odd_respell の紫の読み直しに使う（2026-11-09 手分けA）。例は作った文。
ReverseInRespell は odd_respell.py.diff を入れたときだけ通る。"""
import os
import unittest

import ime_reconvert as R


class _Rev:
    available = True

    def __init__(self, rw):
        self.rw = rw

    def reverse_words(self, text):
        return self.rw


RW = ('つたえふたことで', ((0, 2, 0, 3, 0, 0), (2, 4, 3, 7, 0, 0), (4, 5, 7, 8, 0, 0)))


class ImeReverseReading(unittest.TestCase):
    def setUp(self):
        R._IME_REVERSE.clear()
        R._remember_ime_reverse('伝え二言で', _Rev(RW))

    def test_aligned(self):
        self.assertEqual(R.ime_reverse_reading('伝え二言で', 0, 4), 'つたえふたこと')
        self.assertEqual(R.ime_reverse_reading('伝え二言で', 2, 4), 'ふたこと')

    def test_not_aligned_or_other_line(self):
        self.assertIsNone(R.ime_reverse_reading('伝え二言で', 3, 4))
        self.assertIsNone(R.ime_reverse_reading('別の行', 0, 2))

    def test_switch(self):
        os.environ['CN_IME_REVERSE_READING'] = '0'
        try:
            self.assertIsNone(R.ime_reverse_reading('伝え二言で', 0, 4))
        finally:
            del os.environ['CN_IME_REVERSE_READING']


class ReverseInRespell(unittest.TestCase):
    def test_span_reading_uses_ime(self):
        import odd_respell as O
        R._IME_REVERSE.clear()
        R._remember_ime_reverse('伝え二言で', _Rev(RW))
        self.assertEqual(O._span_reading('伝え二言で', 0, 4), (0, 4, ['つたえふたこと']))
        R._IME_REVERSE.clear()
        self.assertNotEqual(O._span_reading('伝え二言で', 0, 4), (0, 4, ['つたえふたこと']))


if __name__ == '__main__':
    unittest.main()
