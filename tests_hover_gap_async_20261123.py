# -*- coding: utf-8 -*-
"""行と行の間のオンマウスを本体で待たずに作る（2026-11-23・軽量化。解析の最中のオンマウスで本体が 100〜260ms 止まって
いた）。子が空いている行と行の間に待たない頼みを出し、答えがそろうまで次の行を頼まない（app._analyze_slice が待つ）。
CN_HOVER_GAP_ASYNC=0 で前の形。Tk の窓は作らない（作り物のアプリ）。"""
import os
import time
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app
import auto_candidates as AC


class Gap(unittest.TestCase):
    def test_hold_while_asks_are_pending(self):
        a = NS(_hover_asks=dict(gap=True, pending={'k': 3}, since=time.monotonic()), _async_request=None)
        self.assertTrue(AC.hold_analysis(a))
        a._hover_asks['since'] = time.monotonic() - AC.HOVER_ASK_TIMEOUT_S - 1
        self.assertFalse(AC.hold_analysis(a))                   # 待ちは長くても HOVER_ASK_TIMEOUT_S
        a._hover_asks = dict(gap=True, pending={}, since=time.monotonic())
        self.assertFalse(AC.hold_analysis(a))                   # 答えがそろった
        a._hover_asks = dict(gap=False, pending={'k': 3}, since=time.monotonic())
        self.assertFalse(AC.hold_analysis(a))                   # 行と行の間に出した頼みではない
        with mock.patch.dict(os.environ, {'CN_HOVER_GAP_ASYNC': '0'}):
            a._hover_asks = dict(gap=True, pending={'k': 3}, since=time.monotonic())
            self.assertFalse(AC.hold_analysis(a))

    def test_the_hold_always_comes_off(self):
        # 今日の「解析が止まる」と同じ形（答えが来ないまま待ち続ける）にならない: 子が作り直された・閉じた・
        # タブを替えて解析の段取りが変わった・本体の頼みが出ている時は、待ちを外す
        alive = NS(closed=False, process=NS(is_alive=lambda: True))

        def app_with(**kw):
            a = NS(_correction_worker=alive, _analyze_work='W1', _async_request=None, _analyze_pos=10,
                   _analyze_todo=list(range(100)))
            a._hover_asks = dict(gap=True, pending={'k': 3}, since=time.monotonic(), worker=alive, work='W1')
            for k, v in kw.items():
                setattr(a, k, v)
            return a
        self.assertTrue(AC.hold_analysis(app_with()))
        self.assertFalse(AC.hold_analysis(app_with(_correction_worker=NS(closed=False, process=NS(is_alive=lambda: True)))))
        dead = NS(closed=False, process=NS(is_alive=lambda: False))
        a = app_with(_correction_worker=dead)
        a._hover_asks['worker'] = dead
        self.assertFalse(AC.hold_analysis(a))                    # 子がいない
        closed = NS(closed=True, process=NS(is_alive=lambda: True))
        a = app_with(_correction_worker=closed)
        a._hover_asks['worker'] = closed
        self.assertFalse(AC.hold_analysis(a))                    # 子を閉じた
        self.assertFalse(AC.hold_analysis(app_with(_analyze_work='W2')))    # タブを替えた・段取りが変わった
        self.assertFalse(AC.hold_analysis(app_with(_async_request=('line',))))

    def test_hovers_in_a_row_do_not_stop_the_analysis(self):
        # 前の待ちの後に解析が1行も進んでいなければ、新しい待ちには入らない
        alive = NS(closed=False, process=NS(is_alive=lambda: True))
        a = NS(_correction_worker=alive, _analyze_work='W', _async_request=None, _analyze_pos=10,
               _analyze_todo=list(range(100)))
        a._hover_asks = dict(gap=True, pending={'k': 1}, since=time.monotonic(), worker=alive, work='W')
        self.assertTrue(AC.hold_analysis(a))                      # 1つ目の待ち
        a._hover_asks = dict(gap=True, pending={'k': 2}, since=time.monotonic(), worker=alive, work='W')
        self.assertFalse(AC.hold_analysis(a))                     # 次のオンマウス: まだ1行も進んでいない
        a._analyze_pos = 11
        a._hover_asks = dict(gap=True, pending={'k': 3}, since=time.monotonic(), worker=alive, work='W')
        self.assertTrue(AC.hold_analysis(a))                      # 1行進んだら、また待てる

    def test_between_rows_asks_without_waiting_and_holds(self):
        seen = {}

        def fake_show(app_, widget, key, snap, between_rows=False, idle_child=False):
            seen.update(between_rows=between_rows, idle_child=idle_child)
            app_._hover_asks = dict(key=key, pending={'t': 9}, got={}, done={}, since=time.monotonic())
            return False                                         # 頼みを出して抜けた（_Deferred）
        a = NS(_hover_waiting=('w', 'k', dict(busy_since=time.monotonic())), _async_request=None,
               _cn_in_analyze_slice=True)
        with mock.patch.object(AC, 'hover_show', fake_show):
            with self.assertRaises(AC.HoldAnalysis):
                AC.run_waiting_hover(a)
        self.assertEqual(seen, dict(between_rows=True, idle_child=False))   # 本体で待たない頼み
        self.assertTrue(a._hover_asks['gap'])
        self.assertTrue(AC.hold_analysis(a))

    def test_analyze_slice_takes_the_hold(self):
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        calls = []

        def step(app_, count):
            calls.append(count)
            raise AC.HoldAnalysis()
        with mock.patch.object(app.analysis_async, 'line_step', step), \
                mock.patch.object(AC, 'hold_analysis', lambda app_: False):
            app.CorrectNoteApp._analyze_slice(a, 1)              # 受けて抜ける（外へ出さない）
        self.assertEqual(calls, [1])
        self.assertFalse(a._cn_in_analyze_slice)
        with mock.patch.object(app.analysis_async, 'line_step', step), \
                mock.patch.object(AC, 'hold_analysis', lambda app_: True):
            app.CorrectNoteApp._analyze_slice(a, 1)              # 待っている間は行を頼まない
        self.assertEqual(calls, [1])

    def test_switch_back_waits_on_the_main_thread(self):
        seen = {}

        def fake_show(app_, widget, key, snap, between_rows=False, idle_child=False):
            seen.update(idle_child=idle_child)
            return True
        a = NS(_hover_waiting=('w', 'k', dict(busy_since=time.monotonic())), _async_request=None,
               _cn_in_analyze_slice=True)
        with mock.patch.dict(os.environ, {'CN_HOVER_GAP_ASYNC': '0'}), mock.patch.object(AC, 'hover_show', fake_show):
            self.assertTrue(AC.run_waiting_hover(a))
        self.assertEqual(seen, dict(idle_child=True))


if __name__ == '__main__':
    unittest.main()
