"""correction_entry._vowel_added: 漢字は一番短い読みの打鍵で数える（作った例）。"""
import os
import unittest

import correction_entry as CE


class VowelAddedShortTest(unittest.TestCase):
    def test_short_reading(self):
        # 倉kもに → 倉庫に: 庫 は こ（2打）で、k＋も（3打）より増えていない
        self.assertFalse(CE._vowel_added('倉kもに', '倉庫に', 1, 'k'))

    def test_switch_off(self):
        os.environ['CN_VOWEL_ADDED_SHORT'] = '0'
        try:
            self.assertTrue(CE._vowel_added('倉kもに', '倉庫に', 1, 'k'))
        finally:
            del os.environ['CN_VOWEL_ADDED_SHORT']


if __name__ == '__main__':
    unittest.main()
