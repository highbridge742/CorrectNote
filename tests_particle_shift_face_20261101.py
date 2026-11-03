# -*- coding: utf-8 -*-
"""助詞の を を、隣のキーの ほ と打った所（隣＋シフトの2打）。隣の へ だけが候補に残って決まっていたのを、
シフト面のかなも候補に入れ、名詞＋助詞＋述語の例文の組で決める（impossible_slip・2026-11-01 B）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import correction_entry as CE
import impossible_slip as I


def _line(st, line):
    return CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                           decisions=st.decisions, context_vec=st.context_vec)


class ParticleShiftFaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def test_object_particle_restored(self):
        for line, want in [('手紙ほ書いた。', '手紙を書いた。'), ('窓ほ開けた。', '窓を開けた。'),
                           ('本ほ読んだ。', '本を読んだ。'), ('写真ほ撮った。', '写真を撮った。'),
                           ('旅行の予定ほ立てた。', '旅行の予定を立てた。')]:
            self.assertEqual(_line(self.st, line)['corrected'], want, line)

    def test_direction_particle_kept_when_pairs_say_so(self):
        for line, want in [('駅ほ向かった。', '駅へ向かった。'), ('学校ほ行った。', '学校へ行った。')]:
            self.assertEqual(_line(self.st, line)['corrected'], want, line)

    def test_pair_sides_when_exact_pair_missing(self):
        # 名詞＋助詞＋述語の組そのものは無いが、助詞＋述語・名詞＋助詞の両方で を だけが在る
        self.assertEqual(_line(self.st, '甘い物ほ控えた。')['corrected'], '甘い物を控えた。')

    def test_correct_lines_untouched(self):
        for line in ['駅へ向かった。', '家へ帰った。', '友達を待った。', '大阪へ行く。']:
            r = _line(self.st, line)
            self.assertEqual(r['corrected'], line, line)
            self.assertFalse(r.get('odd_spans'), line)

    def test_shift_face_added_only_for_neighbor_keys(self):
        alts = I._with_shift_face([('ほ', 0.0), ('ぼ', 0.4), ('わ', 1.0), ('へ', 1.0)])
        self.assertIn(('を', 1.3), alts)
        self.assertEqual(len([a for a, _ in alts if a == 'を']), 1)


class ParticleRivalTests(unittest.TestCase):
    def test_one_particle_rival_decided_by_pairs(self):
        # 同じ所の助詞1字だけ違う二番（どちらも1打違い）は、名詞＋助詞・助詞＋後ろの述語の例文の組で決める（odd_respell）
        import odd_respell as O
        x, y = '週末の発表会は大阪で行われます。', '週末の発表会と大阪で行われます。'
        self.assertEqual(O._particle_rival(x, y), x)
        self.assertEqual(O._particle_rival(y, x), x)
        self.assertIsNone(O._particle_rival(x, '週末の発表会は京都で行われます。'))


class LineEndObjectTests(unittest.TestCase):
    def test_shift_face_repairs_in_odd_respell(self):
        # 紫の所の読みにも、隣＋シフトの2打（ほ → を）の戻しを当てる
        import odd_respell as O
        self.assertIn('ほんを', O._shift_face_repairs('ほんほ'))
        self.assertEqual(O._shift_face_repairs('かき'), [])


class YoonRivalTests(unittest.TestCase):
    def test_small_yoon_after_non_i_row_has_sub_rival(self):
        # 付けられない字の後ろの ゅ を抜く戻しは、前の字をイ段に替える戻しが候補に在れば決めない（last_keystroke）
        import last_keystroke as LK
        pool = [(0, 0, 0, 'まちのしゅうり', 'sub', 3), (0, 0, 0, 'まちのさうり', 'del', 4)]
        self.assertTrue(LK._yoon_rival('まちのさゅうり', 4, pool))
        self.assertFalse(LK._yoon_rival('まちのしゅうり', 4, pool))
        self.assertFalse(LK._yoon_rival('まちのさゅうり', 4, pool[1:]))


if __name__ == '__main__':
    unittest.main()
