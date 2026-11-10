"""ローマ字の1行に打ち違いが2つ（作った例）・同じ読みの選び違い・y の隣のキー（2026-11-10 1.18.2）。"""
import os
import unittest

import odd_respell as O


class PickSameReadingTests(unittest.TestCase):
    def test_same_reading_clean_face_wins_over_rare_face(self):
        s = O._Seen({'来襲の予定を確認する': (100, False), '来週の予定を確認する': (150, True),
                     '雷雨州の予定を確認する': (9000, False)})
        self.assertEqual(O._pick(s)[0], '来週の予定を確認する')

    def test_same_reading_both_clean_common_face(self):
        s = O._Seen({'来襲の予定を確認する': (100, True), '来週の予定を確認する': (150, True)})
        self.assertEqual(O._pick(s)[0], '来週の予定を確認する')

    def test_switch_off(self):
        os.environ['CN_PICK_SAME_READING_OK'] = '0'
        try:
            s = O._Seen({'来襲の予定を確認する': (100, False), '来週の予定を確認する': (150, True)})
            self.assertIsNone(O._pick(s))
        finally:
            del os.environ['CN_PICK_SAME_READING_OK']


class SplitSmallKanaVerbTests(unittest.TestCase):
    def test_verb_cut_before_small_kana_is_not_kana_verb(self):
        self.assertEqual(O._common_kana_verbs('おひりゅはパス板を食べた'), [])

    def test_real_kana_verb_kept(self):
        self.assertTrue(O._common_kana_verbs('ほしがるだけの人'))


class FixesOtherOddTests(unittest.TestCase):
    def test_other_purple_fixed_outside_span(self):
        cur = 'おひりゅはパス板を食べた'
        self.assertTrue(O._fixes_other_odd(cur, 'お昼はパス板を食べた', 'お昼はパスタを食べた', 0, 4,
                                           [(0, 5, False, 0), (3, 7, False, 0)]))

    def test_change_inside_fixed_span_not_counted(self):
        cur = 'おひりゅはパス板を食べた'
        self.assertFalse(O._fixes_other_odd(cur, 'お昼はパス板を食べた', 'お肥はパス板を食べた', 0, 4,
                                            [(0, 5, False, 0)]))


class ImeRareFaceTests(unittest.TestCase):
    def test_rarer_ime_face_not_taken(self):
        import correction_entry as CE
        self.assertTrue(CE._ime_face_rarer('来週の予定を確認する', '来襲の予定を確認する'))
        self.assertFalse(CE._ime_face_rarer('見て下さい', '見てください'))

    def test_other_ime_face_part_still_taken(self):
        import correction_entry as CE
        from unittest import mock
        with mock.patch('ime_reconvert.ime_face', lambda b, f: '来襲の予定を見てください'):
            r = CE._respell_ime_face('x', {'corrected': 'らいj州の予定を見て下さい'},
                                     {'corrected': '来週の予定を見て下さい', 'details': []})
        self.assertEqual(r['corrected'], '来週の予定を見てください')


if __name__ == '__main__':
    unittest.main()
