# -*- coding: utf-8 -*-
"""打った読みの記録があるとき、直した欄の読みが打った読みから1打（2打の戻しなら2打）より離れた答えは決めない（odd_respell・手分けA・2026-11-01）。作った例だけ。"""
import unittest
import kanji_guess
import odd_respell as O


class TypedDistanceTests(unittest.TestCase):
    def setUp(self):
        self.old = kanji_guess._IME_READINGS_PROVIDER
        mp = {'窓': ['まど'], '開け手': ['あけて'], '下さい': ['ください'], '花瓶': ['かびん'], '買う': ['かう']}
        kanji_guess._IME_READINGS_PROVIDER = lambda s: mp.get(s, [])

    def tearDown(self):
        kanji_guess._IME_READINGS_PROVIDER = self.old

    def test_typed_reading_of_field(self):
        self.assertEqual(O._typed_field_reading('窓を開け手下さい'), 'まどをあけてください')

    def test_keys_split_voiced_marks(self):
        # かな入力では で＝て＋゛ の2打
        self.assertEqual(O._key_distance(O._keys('か'), O._keys('で')), 2)
        self.assertEqual(O._key_distance(O._keys('て'), O._keys('で')), 1)

    def test_far_answer_is_not_decided(self):
        # 打った読み かびん から2打離れた答え（かばん→かいばん 相当）は決めない、1打なら決めてよい
        self.assertTrue(O._far_from_typed('花瓶を買う', 'かいばんを買う'))
        self.assertFalse(O._far_from_typed('花瓶を買う', 'かばんを買う'))

    def test_no_record_no_check(self):
        kanji_guess._IME_READINGS_PROVIDER = lambda s: []
        self.assertFalse(O._far_from_typed('花瓶を買う', 'かいばんを買う'))


if __name__ == '__main__':
    unittest.main()
