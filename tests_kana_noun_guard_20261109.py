# -*- coding: utf-8 -*-
"""batch420: 漢字に変換された身近な語の所をひらがなの名詞に替える直しは戻す（_kana_noun_from_kanji_guard）。"""
import os
import unittest

import correction_entry as CE


class KanaNounGuard(unittest.TestCase):
    def test_revert(self):
        line = 'それは言う間に終わった。'
        out = CE._kana_noun_from_kanji_guard(line, {'corrected': 'それはいまに終わった。', 'changed': True}, None)
        self.assertEqual(out['corrected'], line)

    def test_particle_kept(self):
        line = '台風李影響で遅れた。'
        res = {'corrected': '台風の影響で遅れた。', 'changed': True}
        self.assertEqual(CE._kana_noun_from_kanji_guard(line, res, None)['corrected'], '台風の影響で遅れた。')

    def test_switch_off(self):
        os.environ['CN_KANA_NOUN_GUARD'] = '0'
        try:
            line = 'それは言う間に終わった。'
            res = {'corrected': 'それはいまに終わった。', 'changed': True}
            self.assertEqual(CE._kana_noun_from_kanji_guard(line, res, None)['corrected'], 'それはいまに終わった。')
        finally:
            del os.environ['CN_KANA_NOUN_GUARD']


if __name__ == '__main__':
    unittest.main()
