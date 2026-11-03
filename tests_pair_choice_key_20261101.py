# -*- coding: utf-8 -*-
"""語の組の段（pair_choice）を、読みが1打違いの名詞にも広げた形（2026-11-01）。作った文だけ。"""
import unittest
import pair_choice as P


class PairChoiceKeyTests(unittest.TestCase):
    def test_rare_noun_one_key_from_a_paired_noun_is_fixed(self):
        # ほんじ（例文に無い稀な語）→ へんじ（を 返事 書く の組が例文に在る）
        self.assertEqual(P.propose('友達からの手紙に本字を書いた。'), [(8, 10, '返事')])

    def test_only_kana_input(self):
        self.assertEqual(P.propose('友達からの手紙に本字を書いた。', 'romaji'), [])

    def test_everyday_lines_are_kept(self):
        for line in ('その課題を説明する。', '計画を実行に移す。', '手紙の返事を書いた。'):
            self.assertEqual(P.propose(line), [], line)


if __name__ == '__main__':
    unittest.main()
