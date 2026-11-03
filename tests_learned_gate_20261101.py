# -*- coding: utf-8 -*-
"""覚えた語がかなの欄の紫を消した所の見直し（learned_gate・2026-11-01・手分けA）。作った例だけ。"""
import unittest
from tests_analysis_async import initial
import learned_gate as L


class LearnedGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()
        # 作った「覚えた語」: 同梱の語彙に無い語を2回足して立てる
        cls.st.store.add('かくじ', '角地')
        cls.st.store.add('かくじ', '角地')

    def test_learned_word_with_unlisted_neighbour_goes_back_to_kana(self):
        # 覚えた語＋隣の名詞の組が辞書にも無く、1打違いのよく使う読み（かんじ）がある → かなに戻して紫
        self.assertEqual(L.propose('かくじへんかん', '角地変換', self.st.store), [(0, 4, 'かくじへんかん')])
        r = L.repair_line('かくじへんかん', {'corrected': '角地変換', 'odd_spans': []}, self.st.store)
        self.assertEqual(r['corrected'], 'かくじへんかん')
        self.assertEqual(r['odd_spans'], [(0, 7)])

    def test_not_learned_word_untouched(self):
        # 同梱の語彙で立っている語は見ない
        self.assertEqual(L.propose('かんじへんかん', '漢字変換', self.st.store), [])

    def test_no_noun_neighbour_untouched(self):
        # 隣が名詞でない（助詞を挟む）所は見ない
        self.assertEqual(L.propose('かくじのとち', '角地の土地', self.st.store), [])

    def test_reading_changed_untouched(self):
        # 読みを替えた直しは見ない
        self.assertEqual(L.propose('かくしへんかん', '角地変換', self.st.store), [])

    def test_dictionary_compound_passes(self):
        # 覚えた語＋隣の名詞が辞書の1語なら通す
        import seed_japanese
        old = seed_japanese.is_unit
        seed_japanese.is_unit = lambda s: True if s == '角地変換' else old(s)
        try:
            self.assertEqual(L.propose('かくじへんかん', '角地変換', self.st.store), [])
        finally:
            seed_japanese.is_unit = old


if __name__ == '__main__':
    unittest.main()
