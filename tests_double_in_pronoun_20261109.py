# -*- coding: utf-8 -*-
"""last_keystroke: 同じ字の2つが代名詞（ここ）の中なら「1字余り」の紫を付けない（2026-11-09）。作り例だけ。"""
import unittest

import last_keystroke as LK


class T(unittest.TestCase):
    def test_pronoun(self):
        import morphology
        line = 'ここから続きを書きます。'
        spans = LK._impossible_kana_spans(line, list(morphology.tokenize(line)))
        self.assertFalse(any('1字余って' in s[2] for s in spans))

    def test_switch(self):
        import os
        import morphology
        os.environ['CN_DOUBLE_IN_PRONOUN'] = '0'
        try:
            line = 'ここから続きを書きます。'
            spans = LK._impossible_kana_spans(line, list(morphology.tokenize(line)))
            self.assertTrue(any('1字余って' in s[2] for s in spans))
        finally:
            del os.environ['CN_DOUBLE_IN_PRONOUN']


if __name__ == '__main__':
    unittest.main()
