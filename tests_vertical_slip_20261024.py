"""かな入力の置き換えに「同じ指の1段上・下」を入れる（2026-10-24）。

うにさん 10-24「縦も入れる方向で詰める」「入れたうえでまた考える」。
一般のタイピングの誤りでは、置き換えは同じ段の左右が最多、次が同じ指の上下。
斜め（隣の指の上下）は入れない。ローマ字（QWERTY）の隣は変えない。
"""
import unittest

import kana_layout as KL
import keyboard_layout as K
import corrector as C


class VerticalSlipTest(unittest.TestCase):
    def test_same_row_still_adjacent(self):
        self.assertEqual(KL.kana_key_distance('か', 'す'), 1.0)
        self.assertEqual(KL.kana_key_distance('の', 'ま'), 1.0)

    def test_same_finger_vertical_is_adjacent(self):
        # 人差し指: か(T) と き(G)、中指: に(I) と の(K)、小指: れ(;) と め(/)
        for a, b in (('か', 'き'), ('に', 'の'), ('れ', 'め'), ('た', 'ち')):
            self.assertEqual(KL.kana_key_distance(a, b), KL.VERTICAL_DISTANCE, (a, b))   # 横（1.0）より一段弱い
            self.assertTrue(C.adjacent_slip(a, b, 'kana'), (a, b))

    def test_vertical_is_one_step_weaker_than_horizontal(self):
        self.assertGreater(KL.VERTICAL_DISTANCE, 1.0)
        self.assertLessEqual(KL.VERTICAL_DISTANCE, 1.05)

    def test_diagonal_and_two_rows_stay_far(self):
        # か(T) と く(H) は別の指の斜め、か と こ は2段
        for a, b in (('か', 'く'), ('か', 'こ'), ('う', 'し')):
            self.assertGreater(KL.kana_key_distance(a, b), 1.6, (a, b))

    def test_other_hand_is_not_vertical(self):
        # か(T・左の人差し指) と み(N・右の人差し指)は上下でも手が違う
        self.assertGreater(KL.kana_key_distance('か', 'み'), 1.6)

    def test_mark_key_neighbors_include_vertical(self):
        near = set(KL.mark_key_neighbors('゛'))
        self.assertIn('せ', near)
        self.assertIn('け', near)

    def test_romaji_neighbors_unchanged(self):
        near = K.near_pairs()
        self.assertIn(('f', 'g'), near)
        self.assertNotIn(('r', 'f'), near)
        self.assertNotIn(('u', 'j'), near)

    def test_word_repair_by_vertical_slip(self):
        # 作った例: たべもの の き を か と打った形の1字（同じ指の上）
        self.assertTrue(C._adj_ok_one_char('かのう', 'きのう', 'kana'))


if __name__ == '__main__':
    unittest.main()
