# -*- coding: utf-8 -*-
"""last_keystroke の読み直しが紫の外の正しい語を同じ読みの別の表記に替えた所は元に戻す（_keep_outside・2026-11-01 手分けB）。作った例だけ。"""
import unittest
import last_keystroke as LK


class KeepOutsideTests(unittest.TestCase):
    def test_same_reading_respelling_outside_purple_is_restored(self):
        line = '図書館で本お読む'
        result = {'corrected': line, 'odd_spans': [(5, 6)]}
        out = {'corrected': 'としょかんで本を読む', 'details': [('お', 'を', 'かな入力')]}
        got = LK._keep_outside(line, result, out)
        self.assertEqual(got['corrected'], '図書館で本を読む')

    def test_change_inside_purple_is_kept(self):
        line = '図書館で本お読む'
        result = {'corrected': line, 'odd_spans': [(5, 6)]}
        out = {'corrected': '図書館で本を読む'}
        self.assertIs(LK._keep_outside(line, result, out), out)

    def test_only_respelling_returns_entry_answer(self):
        line = '図書館で本お読む'
        result = {'corrected': line, 'odd_spans': [(5, 6)]}
        out = {'corrected': 'としょかんで本お読む'}
        self.assertIs(LK._keep_outside(line, result, out), result)


if __name__ == '__main__':
    unittest.main()
