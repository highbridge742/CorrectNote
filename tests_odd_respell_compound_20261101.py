# -*- coding: utf-8 -*-
"""打った読みのまま辞書の複合語（名詞＋名詞）として読めるかなの所は、1打違いの別の語に替えない（odd_respell・手分けA・2026-11-01）。作った例だけ。"""
import unittest
import odd_respell as O


class DictCompoundKanaTests(unittest.TestCase):
    def test_dictionary_compound_reading(self):
        # 天気＋予報・交通＋事故 は辞書の見出しの複合語
        self.assertTrue(O._dict_compound_kana('てんきよほう', 0, 2))
        self.assertTrue(O._dict_compound_kana('あしたのこうつうじこ', 5, 7))

    def test_not_a_dictionary_compound(self):
        # 名詞＋名詞でも辞書の見出しに無い組・名詞1つの読みは決め手にしない
        self.assertFalse(O._dict_compound_kana('おんどけいさん', 0, 2))
        self.assertFalse(O._dict_compound_kana('ながいはなし', 0, 2))

    def test_one_kanji_nouns_do_not_count(self):
        # 1字の名詞の組（1語の読みと変わらない）は数えない
        self.assertEqual({f for f in O._noun_faces('えん') if len(f) < 2}, set())


if __name__ == '__main__':
    unittest.main()
