# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""文節の読み直し（repair_ime_clause）で、入口が文節より前も直したときの位置の写しと、
文節の頭の助詞を外した辞書引き（補正担当・2026-10-25。逆効果 取り掛かする の直し）。例文は作ったもの。"""
import unittest

import last_keystroke as LK


class _Dict:
    def __init__(self, words):
        self.words = set(words)

    def is_world_reading(self, reading):
        return reading in self.words

    def inflected_surfaces_for_reading(self, reading):
        return []


class MappedStartTests(unittest.TestCase):
    def test_unchanged_text_keeps_position(self):
        self.assertEqual(LK._mapped_start('あいうえお', 3, 'あいうえお'), 3)

    def test_shorter_fix_before_the_clause_moves_the_start_left(self):
        # 入口が文節より前を1字短く直した（こみれから→これから）: 文節の頭は1つ左へ
        text = 'こみれからかだいにとりかかる。'
        fixed = 'これからかだいにとりかかる。'
        self.assertEqual(LK._mapped_start(text, 8, fixed), 7)
        self.assertEqual(fixed[7:13], text[8:14])

    def test_fix_inside_or_after_the_clause_does_not_move_the_start(self):
        text = 'きょうはかだいにとりかかる。'
        self.assertEqual(LK._mapped_start(text, 7, 'きょうはかだいにとりかかった。'), 7)
        self.assertEqual(LK._mapped_start(text, 7, 'きょうは課題にとりかかる。'), 6)


class KnownKanaWordHeadTests(unittest.TestCase):
    def test_head_particle_is_skipped_only_when_told(self):
        d = _Dict({'とりかかる'})
        face, clause, typed = 'にとりかかる', 'に取り掛かする', 'にとりかかする'
        self.assertFalse(LK._known_kana_word(face, clause, typed, d))
        self.assertTrue(LK._known_kana_word(face, clause, typed, d, head=1))

    def test_shared_first_letter_is_not_a_head(self):
        # 共通の頭の字（し）を勝手に外すと しきゅうでん→きゅうでん が語になってしまう。head を言われない限り外さない
        d = _Dict({'きゅうでん'})
        self.assertFalse(LK._known_kana_word('しきゅうでんを', 'しはゅ腕んを', 'しはゅうでんを', d))


if __name__ == '__main__':
    unittest.main()
