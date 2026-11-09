# -*- coding: utf-8 -*-
"""_fix_lone_kanji_join: 同じ読みの表記の選び直しは、後ろの1字が動詞の頭なら戻さない（2026-11-09）。作り例だけ。"""
import unittest

import correction_entry as C


class T(unittest.TestCase):
    def test_same_reading(self):
        self.assertTrue(C._same_reading_fix('変身', '返信'))
        self.assertTrue(C._same_reading_fix('紀行', '気候'))

    def test_not_same(self):
        self.assertFalse(C._same_reading_fix('身内', '身内'))
        self.assertFalse(C._same_reading_fix('誤解', '五階人'))


if __name__ == '__main__':
    unittest.main()
