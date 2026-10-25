# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""文脈補正の並べ方（contextual_repair.rank_candidates）: 本人が打った読みのまま同梱の表にあるカタカナ語の
中のキーを別のキーに替える手（隣接キー）は、同じ読みで通せる候補より後ろ（2026-10-25）。例文は作ったもの。"""
import unittest

import contextual_repair as CR


def _row(surface, reading_text, segments, operation, position, pressed='', intended=''):
    return dict(surface=surface,
                reading=dict(text=reading_text, source='contextual_token_sequence', rank=0,
                             segments=segments, provenance=()),
                repair=dict(reading=reading_text if operation == 'same_reading' else reading_text,
                            operation=operation, position=position, pressed=pressed, intended=intended,
                            cost=0.0 if operation == 'same_reading' else 1.0),
                rank_evidence=dict(input_reading=0, direct=3, usage=None, start=0, end=5, edits=0 if operation == 'same_reading' else 1,
                                   added=0, physical=0, native_predicate=0, source_relation=0, written_boundary=0, meaning=0,
                                   written_native=0, native_inflection=0, method_spelling=0, bases=0, script=0, proper=0,
                                   terminal=0, guesses=0, context=0.0, cost=0, local_reading=None, parse_cost=None,
                                   continuation=None),
                context_scope=(0, 8), context_reading_length=8, local_verb_bases=())


class WorldWordBreakTests(unittest.TestCase):
    SEG = ((0, 4, 'ぶろっく', 'literal_kana'), (4, 5, 'し', 'analyzed_word'))

    def test_adjacent_key_inside_a_table_katakana_word_is_marked(self):
        row = _row('ブラックし', 'ぶろっくし', self.SEG, 'adjacent_substitution', 1, 'ろ', 'ら')
        self.assertEqual(CR._world_word_break(row), 1)

    def test_same_reading_candidate_is_not_marked(self):
        row = _row('ブロックし', 'ぶろっくし', self.SEG, 'same_reading', -1)
        self.assertEqual(CR._world_word_break(row), 0)

    def test_key_outside_the_katakana_word_is_not_marked(self):
        row = _row('ブロック死', 'ぶろっくし', self.SEG, 'adjacent_substitution', 4, 'し', 'じ')
        self.assertEqual(CR._world_word_break(row), 0)

    def test_same_reading_outranks_adjacent_key_inside_table_word(self):
        a = _row('ブラックし', 'ぶろっくし', self.SEG, 'adjacent_substitution', 1, 'ろ', 'ら')
        b = _row('ブロックし', 'ぶろっくし', self.SEG, 'same_reading', -1)
        # 読みの費用では隣接キーの側が安い（PC で起きた形）
        a['rank_evidence']['local_reading'] = 2.7; b['rank_evidence']['local_reading'] = 3.5
        a['rank_evidence']['parse_cost'] = 6000; b['rank_evidence']['parse_cost'] = 7000
        ordered = CR.rank_candidates([a, b])
        self.assertEqual(ordered[0]['surface'], 'ブロックし')


if __name__ == '__main__':
    unittest.main()
