"""correction_entry._letters_mean_romaji: かな・漢字に挟まれた半角の英字はローマ字の跡（作った例）。"""
import os
import unittest

import correction_entry as CE


class LettersMeanRomajiTest(unittest.TestCase):
    def test_trace(self):
        self.assertTrue(CE._letters_mean_romaji('らいsひゅの会議'))
        self.assertTrue(CE._letters_mean_romaji('お非ryは家で食べる'))   # 2字も（うに 11-10 01:51Z）

    def test_word_not_trace(self):
        self.assertFalse(CE._letters_mean_romaji('PCの設定を見る'))
        self.assertFalse(CE._letters_mean_romaji('あしたの会議'))

    def test_switch_off(self):
        os.environ['CN_LETTER_MEANS_ROMAJI'] = '0'
        try:
            self.assertFalse(CE._letters_mean_romaji('らいsひゅの会議'))
        finally:
            del os.environ['CN_LETTER_MEANS_ROMAJI']


if __name__ == '__main__':
    unittest.main()
