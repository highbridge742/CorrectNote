# -*- coding: utf-8 -*-
"""稀の紫を消してよいほど本人の語か（last_keystroke._her_word_trusted・2026-10-25）。層3以上の2字漢語は4回以上。作った語だけ。"""
import unittest
import last_keystroke as LK


class _Store(object):
    def __init__(self, table):
        self.table = table
    def lookup(self, reading):
        return self.table.get(reading, [])


class HerWordTrustedTests(unittest.TestCase):
    def test_far_kango_needs_four_uses(self):
        import kango_tier
        if (kango_tier.known_usage_tier('一世') or 9) <= 2:
            self.skipTest('身近さの表の判定が前提と違う')
        two = _Store({'いっせ': [{'surface': '一世', 'count': 2, 'solid': True}]})
        four = _Store({'いっせ': [{'surface': '一世', 'count': 4, 'solid': True}]})
        self.assertFalse(LK._her_word_trusted(two, 'いっせ', '一世'))
        self.assertTrue(LK._her_word_trusted(four, 'いっせ', '一世'))

    def test_everyday_kango_keeps_two_uses(self):
        import kango_tier
        if kango_tier.known_usage_tier('高校') != 1:
            self.skipTest('身近さの表の判定が前提と違う')
        two = _Store({'こうこう': [{'surface': '高校', 'count': 2, 'solid': True}]})
        self.assertTrue(LK._her_word_trusted(two, 'こうこう', '高校'))

    def test_non_kango_word_is_as_before(self):
        two = _Store({'たびさき': [{'surface': '旅先', 'count': 2, 'solid': True}]})
        self.assertEqual(LK._her_word_trusted(two, 'たびさき', '旅先'), LK._her_word(two, 'たびさき', '旅先'))

    def test_unknown_word_is_not_trusted(self):
        self.assertFalse(LK._her_word_trusted(_Store({}), 'いっせ', '一世'))


if __name__ == '__main__':
    unittest.main()
