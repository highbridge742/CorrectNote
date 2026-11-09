"""ime_reconvert._typed_real_noun: 打ったとおりの読みで実在の名詞が出ている窓は、1打の戻しの根拠にしない（作った例）。"""
import os
import unittest

import ime_reconvert as R
from morphology import tokenize


class TypedRealNounTest(unittest.TestCase):
    def test_real_noun_as_typed(self):
        t = '自炊の日'
        self.assertTrue(R._typed_real_noun(t, 0, 3, 'じすいの', tokenize(t)))

    def test_other_reading_is_not(self):
        t = '自炊の日'
        self.assertFalse(R._typed_real_noun(t, 0, 3, 'しすいの', tokenize(t)))

    def test_switch_off(self):
        t = '自炊の日'
        os.environ['CN_RECONVERT_TYPED_REAL'] = '0'
        try:
            self.assertFalse(R._typed_real_noun(t, 0, 3, 'じすいの', tokenize(t)))
        finally:
            del os.environ['CN_RECONVERT_TYPED_REAL']


if __name__ == '__main__':
    unittest.main()
