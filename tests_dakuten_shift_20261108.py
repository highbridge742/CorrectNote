"""dakuten_shift: かな入力で ゛ を隣の字に付けた所を戻す（2026-11-08 補正担当）。例は作り例。"""
import unittest

import dakuten_shift as D


class DakutenShiftTest(unittest.TestCase):
    def test_shifts(self):
        self.assertIn('はじめる', D.shifts('ばしめる'))

    def test_verb(self):
        self.assertEqual(D.propose('明日から仕事をば占める。'), [(7, 11, '始める')])

    def test_noun(self):
        self.assertEqual(D.propose('週末の予定をが即で決めた。')[:1], [(6, 8, '家族')])

    def test_correct_lines(self):
        for t in ('部屋の窓を閉める。', '家族で話し合った。', '雑誌を読んだ。', 'いつ告ったの？'):
            self.assertEqual(D.propose(t), [], t)

    def test_voiced_kanji_kept(self):
        self.assertEqual(D.propose('説明を読んでく題'), [])


if __name__ == '__main__':
    unittest.main()
