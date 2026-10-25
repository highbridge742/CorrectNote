# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""keystroke_doubt（打鍵の間隔で巻き込みを疑う・1.16）の見張り。作った文だけ。janome が無くても動く部分を見る。"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keystroke_doubt as KD


class StrokeClockTest(unittest.TestCase):
    def test_ime_press_paired_with_release(self):
        c = KD.StrokeClock(lambda k: {65: 'a', 83: 's'}.get(k))
        c.press(229, 0.0); c.press(229, 5.0)
        c.release(65, 40.0); c.release(83, 45.0)
        self.assertEqual(c.take(), [('a', 0.0), ('s', 5.0)])

    def test_stale_press_dropped(self):
        c = KD.StrokeClock(lambda k: {65: 'a'}.get(k))
        c.press(229, 0.0); c.press(229, 2000.0)
        c.release(65, 2050.0)
        self.assertEqual(c.take(), [('a', 2000.0)])


class DoubtPairsTest(unittest.TestCase):
    POS = {'a': (2, 1), 's': (2, 2), 'k': (2, 8), 'l': (2, 9), 'g': (2, 5), 'h': (2, 6)}
    def adj(self, p, q): return p[0] == q[0] and abs(p[1] - q[1]) == 1

    def test_fast_same_hand_adjacent(self):
        self.assertEqual(KD.doubt_pairs([('a', 0), ('s', 8)], self.POS, self.adj), [(0, 1)])

    def test_slow_not_flagged(self):
        self.assertEqual(KD.doubt_pairs([('a', 0), ('s', 60)], self.POS, self.adj), [])

    def test_center_column_kept(self):
        self.assertEqual(KD.doubt_pairs([('g', 0), ('h', 8)], self.POS, self.adj), [(0, 1)])


class ChooseDropTest(unittest.TestCase):
    def test_impossible_head_decides(self):
        try:
            import kana_rules; kana_rules._load()
        except Exception:
            self.skipTest('語の表（seed_japanese_cost）が無い')
        alt, by_rule = KD.choose_drop(['んあめがふる', 'あめがふる'], lambda s: s, lambda s: 0.0, lambda s: 0)
        self.assertEqual((alt, by_rule), ('あめがふる', True))


class OccurrenceAlternativesTest(unittest.TestCase):
    """補正の入口（correction_entry の occurrence_strokes）に渡る形。作った読みだけ。"""
    def strokes(self, reading, fast):
        import kana_layout as kl, keyboard_layout as kb
        key_at = {p: k for k, p in kb.positions().items()}
        out, t = [], 0.0
        for i, k in enumerate(KD._kana_key_reading(reading)):
            out.append((key_at[kl.KANA_POSITIONS[k]], t)); t += 10.0 if i in fast else 150.0
        return out

    def test_fast_neighbour_gives_both_drops(self):
        self.assertEqual(KD.occurrence_alternatives('あめろ', self.strokes('あめろ', {1}), 'kana'), [('あろ', 'あめ')])

    def test_slow_gives_nothing(self):
        self.assertEqual(KD.occurrence_alternatives('あめろ', self.strokes('あめろ', set()), 'kana'), [])

    def test_strokes_not_matching_reading_ignored(self):
        self.assertEqual(KD.occurrence_alternatives('あめ', self.strokes('あめろ', {1}), 'kana'), [])

    def test_voiced_mark_is_one_stroke(self):
        self.assertEqual(KD._compose_kana(['か', '゛', 'さ']), 'がさ')


if __name__ == '__main__':
    unittest.main()
