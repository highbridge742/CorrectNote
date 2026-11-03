# -*- coding: utf-8 -*-
"""付けられない字の後ろの ゃゅょ を、前の字を替えずに片付けた直しは採らず紫（yoon_slip・2026-11-01 B）。作った例だけ。"""
import unittest
import yoon_slip as Y


class YoonSlipTests(unittest.TestCase):
    def test_spots(self):
        # な の隣に に（イ段）が在る。に＋ゅ はそのまま読める
        self.assertEqual(Y.spots('まちのなゅうす'), [4])
        self.assertEqual(Y.spots('まちのにゅうす'), [])
        # 隣にイ段が無い字の後ろでも、綴りに無い並びなので印にする
        self.assertEqual(Y.spots('まちのそゅうす'), [4])
        self.assertEqual(Y.spots('きゃっと'), [])

    def test_fix_without_i_row_is_reverted_to_purple(self):
        line = 'まちのなゅうす'
        res = {'corrected': 'まちのなうす', 'details': [('ゅ', '', 'かな入力')], 'odd_spans': []}
        out = Y.repair_line(line, res)
        self.assertEqual(out['corrected'], line)
        self.assertTrue(out['odd_spans'])
        self.assertFalse(out['details'])

    def test_fix_with_i_row_yoon_is_kept(self):
        line = 'まちのなゅうす'
        res = {'corrected': 'まちのにゅうす', 'details': [('な', 'に', 'かな入力')], 'odd_spans': []}
        self.assertIs(Y.repair_line(line, res), res)

    def test_other_changes_are_kept(self):
        line = 'まちのなゅうすをよむた'
        res = {'corrected': 'まちのなうすをよんだ', 'details': [], 'odd_spans': []}
        out = Y.repair_line(line, res)
        self.assertEqual(out['corrected'], 'まちのなゅうすをよんだ')

    def test_romaji_untouched(self):
        res = {'corrected': 'x', 'odd_spans': []}
        self.assertIs(Y.repair_line('なゅ', res, input_method='romaji'), res)


if __name__ == '__main__':
    unittest.main()
