# -*- coding: utf-8 -*-
"""_frame_guard: 人の名を 人を取らない 助詞＋動詞 の目的語に置いた形（IME が名字を選んだ）を、同じ読みの身近な名詞に
直した所は、直した形の組が例文に無くても戻さない（2026-11-08 手分けB）。例は作った文。"""
import os
import unittest

import correction_entry as CE


def _res(line, done):
    return {'original': line, 'corrected': done, 'changed': True, 'details': [[line, done, 'test']],
            'odd_spans': []}


class FrameNameObject(unittest.TestCase):
    def test_name_to_noun_kept(self):
        out = CE._frame_guard('昨日の都築を話す', _res('昨日の都築を話す', '昨日の続きを話す'))
        self.assertEqual(out['corrected'], '昨日の続きを話す')

    def test_rare_noun_reverted(self):
        # 直した名詞が名より使われない語（混同）なら前のまま戻して紫
        out = CE._frame_guard('近藤を話す', _res('近藤を話す', '混同を話す'))
        self.assertEqual(out['corrected'], '近藤を話す')
        self.assertTrue(out['odd_spans'])

    def test_switch(self):
        os.environ['CN_FRAME_NAME_OBJECT'] = '0'
        try:
            out = CE._frame_guard('昨日の都築を話す', _res('昨日の都築を話す', '昨日の続きを話す'))
            self.assertEqual(out['corrected'], '昨日の都築を話す')
        finally:
            del os.environ['CN_FRAME_NAME_OBJECT']


if __name__ == '__main__':
    unittest.main()
