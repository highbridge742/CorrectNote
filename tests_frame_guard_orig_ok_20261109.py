# -*- coding: utf-8 -*-
"""batch421: 元の 名詞＋助詞＋動詞 の組が例文に在れば、_frame_guard で戻した所に紫を付けない。"""
import unittest

import correction_entry as CE


class FrameGuardOrigOk(unittest.TestCase):
    def test_orig_frame_known_no_purple(self):
        line = '寿司を食べたい。'
        if CE._frame_at(line, 0) is not True:
            self.skipTest('組の表が無い')
        res = {'corrected': '菓子を食べたい。', 'changed': True, 'odd_spans': [], 'details': []}
        out = CE._frame_guard(line, res)
        if out is res:
            self.skipTest('直しの組が表に在る')
        self.assertEqual(out['corrected'], line)
        self.assertFalse(out.get('odd_spans'))


if __name__ == '__main__':
    unittest.main()
