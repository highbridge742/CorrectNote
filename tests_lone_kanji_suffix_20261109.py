# -*- coding: utf-8 -*-
"""batch430: 直した語の後ろの1字が時・状態の接尾（時・中・後）なら _fix_lone_kanji_join で戻さない。作った例。"""
import os
import unittest

import correction_entry as CE


class LoneKanjiSuffix(unittest.TestCase):
    def test_suffix_kept(self):
        line = '囚虜後に保存します'
        res = {'corrected': '終了後に保存します', 'changed': True, 'odd_spans': [], 'details': []}
        out = CE._fix_lone_kanji_join(line, res, None, None)
        self.assertEqual(out['corrected'], '終了後に保存します')

    def test_switch_off(self):
        os.environ['CN_FIX_LONE_KANJI_SUFFIX'] = '0'
        try:
            line = '囚虜後に保存します'
            res = {'corrected': '終了後に保存します', 'changed': True, 'odd_spans': [], 'details': []}
            out = CE._fix_lone_kanji_join(line, res, None, None)
            self.assertIsNotNone(out)
        finally:
            del os.environ['CN_FIX_LONE_KANJI_SUFFIX']


if __name__ == '__main__':
    unittest.main()
