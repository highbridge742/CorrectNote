# -*- coding: utf-8 -*-
"""候補の何回目で採ったかの集計の、アプリ側の配線（2026-11-10 うにさん「デバッグメニューにチェックボックスを用意。
デフォルトはオフ。…11回という回数をパラメータに出す」）。

  respell_stats   子・本体の take_rank_stats() の形を足し込み、late は200件まで、ファイルへ書いて読み戻せる
  analysis_worker 頼みに本体の (集計のオン・オフ, 回数の上限) を載せ、子はそれを odd_respell に当て、
                  答えに載った集計は merge_usage が本体で足す
  debug_menu      回数の上限の項目（0＝上限なし〜30）は本体の odd_respell.ATTEMPT_LIMIT に当たる。
                  チェックボックスは設定に残して odd_respell.set_rank_stats を呼ぶ
"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

import analysis_worker
import debug_menu
import odd_respell
import respell_stats


class _Settings(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)

    def set(self, k, v):
        self[k] = v

    def save(self):
        pass


class RespellStatsApp(unittest.TestCase):
    def setUp(self):
        respell_stats.clear()
        odd_respell.take_rank_stats()
        self.saved = (odd_respell.RANK_STATS_ON, odd_respell.ATTEMPT_LIMIT)
        self.had_default = getattr(odd_respell, '_CN_DEFAULT_LIMIT', None)

    def tearDown(self):
        odd_respell.set_rank_stats(self.saved[0])
        odd_respell.set_attempt_limit(self.saved[1])
        respell_stats.clear()
        debug_menu._ORIGINAL.pop('respell_attempts', None)
        if self.had_default is None:
            odd_respell.__dict__.pop('_CN_DEFAULT_LIMIT', None)
        else:
            odd_respell._CN_DEFAULT_LIMIT = self.had_default

    def test_merge_save_load(self):
        respell_stats.merge({'rank': {1: 3, '?': 1}, 'tried': {11: 2}, 'late': [[9, 11, 'もと', 'とった']]})
        respell_stats.merge({'rank': {'1': 2}, 'tried': {}, 'late': []})
        respell_stats.merge(None)
        snap = respell_stats.snapshot()
        self.assertEqual(snap['rank'], {'1': 5, '?': 1})
        self.assertEqual(snap['tried'], {'11': 2})
        self.assertIn('9/11  もと → とった', respell_stats.text())
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'respell_rank_stats.json')
            respell_stats.save(path)
            respell_stats.clear()
            respell_stats.load(path)
            self.assertEqual(respell_stats.snapshot(), snap)
            respell_stats.clear()
            respell_stats.save(path)            # 消したあとはファイルも消す
            self.assertFalse(os.path.exists(path))

    def test_late_keeps_newest(self):
        respell_stats.merge({'late': [[8, 11, 'a%d' % i, 'b'] for i in range(250)]})
        late = respell_stats.snapshot()['late']
        self.assertEqual(len(late), respell_stats.LATE_MAX)
        self.assertEqual(late[-1][2], 'a249')

    def test_worker_carries_setting_and_stats(self):
        odd_respell.set_rank_stats(True)
        odd_respell.set_attempt_limit(11)
        self.assertEqual(analysis_worker.respell_setting(), (True, 11))
        odd_respell.set_rank_stats(False)
        odd_respell.set_attempt_limit(0)
        analysis_worker._apply_respell((True, 7))      # 子の側で当てる
        self.assertEqual((odd_respell.RANK_STATS_ON, odd_respell.ATTEMPT_LIMIT), (True, 7))
        odd_respell._CN_DEFAULT_LIMIT = 6              # この子の odd_respell の既定（初めて当てた時に控える）
        analysis_worker._apply_respell(None)           # 本体に値が無い＝この子の既定のまま（上限を 0 へ落とさない）
        self.assertEqual((odd_respell.RANK_STATS_ON, odd_respell.ATTEMPT_LIMIT), (False, 6))
        result = dict(result={}, respell={'rank': {2: 1}, 'tried': {3: 1}, 'late': []})
        analysis_worker.merge_usage(result)
        self.assertNotIn('respell', result)
        self.assertEqual(respell_stats.snapshot()['rank'], {'2': 1})

    def test_menu_item_and_checkbox(self):
        app = SimpleNamespace(settings=_Settings(debug_timings={}))
        self.assertEqual(debug_menu.minimum('respell_attempts'), 0)
        self.assertEqual(debug_menu.maximum('respell_attempts', app), 30)
        self.assertEqual(debug_menu.default('respell_attempts', app), 6)   # 2026-11-10 うにさん「6で進めて」
        odd_respell.set_attempt_limit(0)
        debug_menu.apply(app)                          # 保存に無くても既定の 6 を当てる
        self.assertEqual(odd_respell.ATTEMPT_LIMIT, 6)
        self.assertEqual(analysis_worker.respell_setting()[1], 6)
        debug_menu.set_value(app, 'respell_attempts', 11, save=False)
        self.assertEqual(odd_respell.ATTEMPT_LIMIT, 11)
        self.assertEqual(app.settings['debug_timings'], {'respell_attempts': 11})
        debug_menu.set_value(app, 'respell_attempts', 0, save=False)   # 0＝上限なしも残る（既定ではない）
        self.assertEqual(odd_respell.ATTEMPT_LIMIT, 0)
        self.assertEqual(app.settings['debug_timings'], {'respell_attempts': 0})
        debug_menu.set_value(app, 'respell_attempts', 6, save=False)   # 既定に戻すと保存から外れる
        self.assertEqual(app.settings['debug_timings'], {})
        self.assertEqual(odd_respell.ATTEMPT_LIMIT, 6)
        self.assertFalse(app.settings.get(respell_stats.SETTING))     # 既定はオフ
        debug_menu.choose_rank_stats(app, True)
        self.assertTrue(app.settings[respell_stats.SETTING])
        self.assertTrue(odd_respell.RANK_STATS_ON)


class RespellSetting(unittest.TestCase):
    def test_setting_is_off_by_default_and_kept(self):
        import settings
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'settings.json')
            s = settings.Settings(path)
            self.assertIs(s.get(respell_stats.SETTING), False)
            s.set(respell_stats.SETTING, True)
            s.save(path)
            again = settings.Settings(path)
            again.load(path)
            self.assertIs(again.get(respell_stats.SETTING), True)


if __name__ == '__main__':
    unittest.main()
