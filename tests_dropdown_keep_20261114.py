# -*- coding: utf-8 -*-
"""再変換の候補一覧（2026-11-14 うにさん「再変換の、候補が順に出た後、一度閉じて再度選択すると候補を作り直している。
少し前のは覚えておくはず。それと、候補が増えて縦に伸びると、選択から下側に伸びていた枠が上側にきり替わる」）。
1. 「打ち間違いの可能性」を確かめた答えは、少し前のものを覚えて、開き直した時にすぐ使う（candidate_check の控え）。
2. 開いたあとで伸びても、開いた時の向き（下・上）を保つ（fit_dropdown(keep=True)）。作った値だけ。"""
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import app
import candidate_check
from app import fit_dropdown

PAD, ROW = 4, 20


class KeepSide(unittest.TestCase):
    def test_opened_below_stays_below_when_it_grows(self):
        # 下に 5行分の余地・上に 30行分の余地。開いた時は2行で下。伸びても下のまま、入る行数だけ
        rows, above = fit_dropdown(2, anchor=500, top=0, bottom=604, padding=PAD, row_height=ROW, gap=24)
        self.assertEqual((rows, above), (2, False))
        rows, above = fit_dropdown(20, anchor=500, top=0, bottom=604, padding=PAD, row_height=ROW, gap=24,
                                   above=above, keep=True)
        self.assertFalse(above)
        self.assertEqual(rows, 5)

    def test_opened_above_stays_above(self):
        rows, above = fit_dropdown(20, anchor=500, top=0, bottom=604, padding=PAD, row_height=ROW, gap=24,
                                   above=True, keep=True)
        self.assertTrue(above)
        self.assertEqual(rows, 20)

    def test_switch_off_is_the_old_flip(self):
        with mock.patch.dict(os.environ, {'CN_DROPDOWN_KEEP_SIDE': '0'}):
            rows, above = fit_dropdown(20, anchor=500, top=0, bottom=604, padding=PAD, row_height=ROW, gap=24,
                                       above=False, keep=True)
        self.assertTrue(above)                      # 前の形: 下に入らなければ上へ切り替わる

    def test_opening_still_picks_the_side_that_fits(self):
        rows, above = fit_dropdown(20, anchor=500, top=0, bottom=604, padding=PAD, row_height=ROW, gap=24)
        self.assertTrue(above)                      # 開く時の決め方は前のまま


def _checker():
    fake_app = SimpleNamespace(settings={'input_method': 'kana'}, root=mock.Mock(), _closing=False)
    c = candidate_check.CandidateCheck(fake_app)
    c._schedule = lambda delay: None              # 子は動かさない
    c._schedule_idle_close = lambda: None
    return c


class CheckMemo(unittest.TestCase):
    def setUp(self):
        os.environ.pop('CN_TYPO_CHECK_MEMO', None)

    def test_known_answers_are_used_at_once(self):
        c = _checker()
        line = '文字を撃つ'
        c._remember('文字を打つ', 3, '打', True)
        c._remember('文字を討つ', 3, '討', False)
        passed = []
        c.start(line, [(3, 4, {'surface': '打'}), (3, 4, {'surface': '討'}), (3, 4, {'surface': '射'})],
                lambda cand: passed.append(cand['surface']))
        self.assertEqual(passed, ['打'])          # 通った物はすぐ出る・紫になった物は出ない
        self.assertEqual([j[2] for j in c.jobs], ['射'])    # まだの物だけ確かめる

    def test_answers_survive_closing(self):
        c = _checker()
        c._remember('文字を打つ', 3, '打', True)
        c.cancel()                                  # 一覧を閉じた
        self.assertTrue(c._remembered('文字を打つ', 3, '打'))

    def test_changed_line_or_method_is_not_reused(self):
        c = _checker()
        c._remember('文字を打つ', 3, '打', True)
        self.assertIsNone(c._remembered('文字を打つよ', 3, '打'))
        c.app.settings['input_method'] = 'romaji'
        self.assertIsNone(c._remembered('文字を打つ', 3, '打'))

    def test_old_answers_expire(self):
        c = _checker()
        c._remember('文字を打つ', 3, '打', True)
        key = c._memo_key('文字を打つ', 3, '打')
        c.memo[key] = (True, time.monotonic() - candidate_check.MEMO_SEC - 1)
        self.assertIsNone(c._remembered('文字を打つ', 3, '打'))

    def test_limit(self):
        c = _checker()
        for i in range(candidate_check.MEMO_LIMIT + 5):
            c._remember('行%d' % i, 0, 'x', True)
        self.assertEqual(len(c.memo), candidate_check.MEMO_LIMIT)

    def test_switch_off(self):
        c = _checker()
        with mock.patch.dict(os.environ, {'CN_TYPO_CHECK_MEMO': '0'}):
            c._remember('文字を打つ', 3, '打', True)
            self.assertIsNone(c._remembered('文字を打つ', 3, '打'))
            passed = []
            c.start('文字を撃つ', [(3, 4, {'surface': '打'})], lambda cand: passed.append(cand['surface']))
            self.assertEqual(passed, [])
            self.assertEqual(len(c.jobs), 1)


if __name__ == '__main__':
    unittest.main()
