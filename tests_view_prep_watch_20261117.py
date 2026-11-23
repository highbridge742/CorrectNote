# -*- coding: utf-8 -*-
"""表示準備中の見張り（2026-11-17 うにさん「タブを移動したら表示準備中から一向に進まない」）。作り物の状態で、止まり方
A（窓のドラッグの印が立ったまま）と B（入力の確かめの予約が残ったまま小分けが続きを予約せずに抜けた）を作り、
見張りが小分けを続けさせることを見る。自分の Tk だけ・本文は使わない。"""
import os
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

import app
import view_prep_watch as W


class Fake:
    _view_changing = app.CorrectNoteApp._view_changing
    _window_dragging = app.CorrectNoteApp._window_dragging
    _analyze_chunk = app.CorrectNoteApp._analyze_chunk

    def __init__(self, root, folder):
        self.root = root
        self._scroll_trace_dir = folder
        self._analyze_units_only = True
        self._analyze_todo = list(range(10))
        self._analyze_pos = 0
        self._analyze_job = None
        self._after_id = None
        self._tab_analysis_job = None
        self._tab_warming = False
        self._win_drag = None
        self._native_window_drag = False
        self._view_change_until = 0.0
        self.scheduled = 0
        self.button_down = False

    def _window_drag_button_down(self):
        return self.button_down

    def _schedule_analysis_chunk(self):
        self.scheduled += 1
        self._analyze_job = self.root.after(60000, lambda: None)
        W.arm(self)


class ViewPrepWatch(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.folder = tempfile.TemporaryDirectory()
        self.a = Fake(self.root, self.folder.name)
        env = mock.patch.dict(os.environ, {'CN_REDO_TRACE': '1'})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            self.root.after_cancel(job)
        self.root.destroy()
        self.folder.cleanup()

    def logged(self):
        path = os.path.join(self.folder.name, 'view_prep.log')
        return open(path, encoding='utf-8').read() if os.path.exists(path) else ''

    def test_b_chunk_waits_for_the_input_check_without_dying(self):
        a = self.a
        a._after_id = self.root.after(60000, lambda: None)      # 入力の確かめの予約が残っている
        a._analyze_chunk()
        self.assertEqual(a.scheduled, 1)             # 進めずに、続きを予約して待つ（根の直し）
        self.assertEqual(a._analyze_pos, 0)

    def test_b_before_the_fix_the_chunk_stopped(self):
        a = self.a
        a._after_id = self.root.after(60000, lambda: None)
        with mock.patch.dict(os.environ, {'CN_VIEW_PREP_WATCH': '0'}):
            a._analyze_chunk()                       # 小分けの頭で抜ける: 続きを予約しない（うにさんの見た形）
        self.assertIsNone(a._analyze_job)
        self.assertEqual(a.scheduled, 0)

    def test_b_watch_rescues_a_dead_chain(self):
        a = self.a
        a._after_id = 'after#999999'                 # もう来ない確かめの予約（Tk には無い）・小分けの続きも無い
        self.assertEqual(W.tick(a), 'rescued')
        self.assertEqual(a.scheduled, 1)
        self.assertIsNone(a._after_id)
        self.assertIn('小分けの続きを予約し直した', self.logged())
        self.assertIn('after_set=True', self.logged())

    def test_a_stuck_drag_flag_is_lowered_after_the_button_is_up(self):
        a = self.a
        a._win_drag = (10, 10)
        self.assertTrue(a._view_changing())
        a._analyze_job = self.root.after(60000, lambda: None)     # 小分けは「後で」を繰り返している
        now = time.monotonic()
        self.assertIsNone(W.tick(a, now))
        a.button_down = True
        self.assertIsNone(W.tick(a, now + 2))                    # ボタンが押されている間は本当のドラッグ
        a.button_down = False
        self.assertEqual(W.tick(a, now + 4), 'drag_cleared')
        self.assertFalse(a._view_changing())
        self.assertIn('窓のドラッグの印を下ろした', self.logged())

    def test_no_action_while_the_chunks_are_alive_and_a_stall_is_logged_once(self):
        a = self.a
        a._analyze_job = self.root.after(60000, lambda: None)
        now = time.monotonic()
        os.environ['CN_VIEW_PREP_HEAL'] = '0'          # 外す働きは別の試験で見る（ここは10秒の記録だけ）
        self.addCleanup(os.environ.pop, 'CN_VIEW_PREP_HEAL', None)
        self.assertIsNone(W.tick(a, now))
        self.assertIsNone(W.tick(a, now + 11))
        self.assertIsNone(W.tick(a, now + 12))
        self.assertEqual(self.logged().count('表示準備中が10秒進まない'), 1)
        self.assertEqual(a.scheduled, 0)

    # 2回目（2026-11-17 17:53 うにさん「表示準備中で止まりました」）: 小分けの予約は生きているのに進まない・子は休み
    def test_stall_with_live_chunks_is_healed_once(self):
        a = self.a
        a._analyze_job = self.root.after(60000, lambda: None)
        info = dict(token_ok=True, state_ok=True, request='line', request_age=8.0, bg_paused=False,
                    typed_pending=False, held=False)
        now = time.monotonic()
        with mock.patch.object(W, 'detail', return_value=info), \
                mock.patch('analysis_async.cancel_foreground_request') as cancel:
            self.assertIsNone(W.tick(a, now))
            self.assertEqual(W.tick(a, now + 6), 'healed')
            self.assertIsNone(W.tick(a, now + 7))              # 同じ所では1回だけ
        cancel.assert_called_once_with(a)
        self.assertIn('進まない→cancel_request', self.logged())
        self.assertIn('request=line', self.logged())

    # 3回目（18:26）: 済んでいない行を補正している子（重い行は5秒を超える）の求めは取り消さない
    def test_busy_child_is_not_cancelled(self):
        with mock.patch.dict(os.environ, {'CN_VIEW_PREP_PATIENT': '0'}):    # 前の形（休んだ5秒で取り消す）
            self.busy_then_quiet()

    # 2026-11-21 うにさん「いま解析が、何か詰まっているような状態」: 計算していた子が5秒休んだだけで取り消し、途中までの
    # 計算を捨てていた。一度計算していたら、続けて PATIENT_IDLE_S 秒休むまで取り消さない
    def test_child_that_was_computing_gets_patience(self):
        a = self.a
        a._analyze_job = self.root.after(60000, lambda: None)
        cpu = iter([10.0, 13.0, 13.0, 13.1, 13.1, 13.2, 13.2, 13.3, 13.3, 13.3, 13.3])
        info = dict(token_ok=True, state_ok=True, request='line', request_age=8.0, bg_paused=False,
                    typed_pending=False, held=False)
        now = time.monotonic()

        def detail(app):
            return dict(info, child_busy=W.child_busy(app))
        with mock.patch.object(W, 'child_cpu', side_effect=lambda app: next(cpu)),                 mock.patch.object(W, 'detail', side_effect=detail),                 mock.patch('analysis_async.cancel_foreground_request') as cancel:
            W.tick(a, now)                                  # 止まり始め: CPU 10
            self.assertIsNone(W.tick(a, now + 6))           # 計算中
            self.assertIsNone(W.tick(a, now + 12))          # 休んで6秒: まだ待つ
            self.assertIsNone(W.tick(a, now + 18))          # 休んで12秒: まだ待つ
            cancel.assert_not_called()
            self.assertEqual(W.tick(a, now + 30), 'healed')  # 休んで24秒（PATIENT_IDLE_S を超えた）: 取り消す
        cancel.assert_called_once_with(a)
        self.assertIn('child_idle_s', self.logged())

    def test_never_busy_child_is_still_cancelled_after_5s(self):
        a = self.a
        a._analyze_job = self.root.after(60000, lambda: None)
        cpu = iter([10.0, 10.1, 10.1, 10.1])
        info = dict(token_ok=True, state_ok=True, request='line', request_age=8.0, bg_paused=False,
                    typed_pending=False, held=False)
        now = time.monotonic()

        def detail(app):
            return dict(info, child_busy=W.child_busy(app))
        with mock.patch.object(W, 'child_cpu', side_effect=lambda app: next(cpu)),                 mock.patch.object(W, 'detail', side_effect=detail),                 mock.patch('analysis_async.cancel_foreground_request') as cancel:
            W.tick(a, now)
            self.assertEqual(W.tick(a, now + 6), 'healed')  # 一度も計算していない（求めが届いていない）: 今までどおり
        cancel.assert_called_once_with(a)

    def busy_then_quiet(self):
        a = self.a
        a._analyze_job = self.root.after(60000, lambda: None)
        cpu = iter([10.0, 13.0, 13.0, 13.1, 13.1])
        info = dict(token_ok=True, state_ok=True, request='line', request_age=8.0, bg_paused=False,
                    typed_pending=False, held=False)
        now = time.monotonic()

        def detail(app):
            return dict(info, child_busy=W.child_busy(app))
        with mock.patch.object(W, 'child_cpu', side_effect=lambda app: next(cpu)), \
                mock.patch.object(W, 'detail', side_effect=detail), \
                mock.patch('analysis_async.cancel_foreground_request') as cancel:
            W.tick(a, now)                                  # 止まり始め: CPU 10
            self.assertIsNone(W.tick(a, now + 6))           # 5秒で 3秒使っていた → 計算中: 取り消さない
            cancel.assert_not_called()
            self.assertEqual(W.tick(a, now + 12), 'healed')  # 次の5秒は 0.1 秒だけ → 休んでいる: 取り消す
        cancel.assert_called_once_with(a)
        self.assertIsNone(W.heal(a, dict(info, child_busy=True)))

    def test_label_says_analysing_while_a_row_is_corrected(self):
        import inspect
        src = inspect.getsource(app.CorrectNoteApp._analyze_chunk)
        self.assertIn("CN_VIEW_PREP_LABEL", src)

    def test_heal_reanalyzes_when_the_document_moved(self):
        a = self.a
        called = []
        a._analyze = lambda: called.append(1)
        self.assertEqual(W.heal(a, dict(token_ok=False, state_ok=True)), 'analyze')
        self.assertEqual(called, [1])

    def test_heal_unpauses_and_clears_dead_inertia(self):
        a = self.a
        from types import SimpleNamespace
        a._scroll_inertia = SimpleNamespace(job='after#888888')
        with mock.patch('analysis_async.pause_background') as pause:
            got = W.heal(a, dict(token_ok=True, state_ok=True, bg_paused=True, typed_pending=False, held=True))
        pause.assert_called_once_with(a, False)
        self.assertEqual(got, 'unpause+inertia')
        self.assertIsNone(a._scroll_inertia.job)
        self.assertIsNone(W.heal(a, dict(token_ok=True, state_ok=True, request='line', request_age=1.0)))

    def test_heal_switch(self):
        a = self.a
        a._analyze_job = self.root.after(60000, lambda: None)
        now = time.monotonic()
        with mock.patch.dict(os.environ, {'CN_VIEW_PREP_HEAL': '0'}), \
                mock.patch.object(W, 'heal') as heal:
            W.tick(a, now)
            W.tick(a, now + 6)
        heal.assert_not_called()

    def test_quiet_when_not_preparing_and_switch_back(self):
        a = self.a
        a._analyze_pos = len(a._analyze_todo)
        self.assertIsNone(W.tick(a))
        a._analyze_pos = 0
        with mock.patch.dict(os.environ, {'CN_VIEW_PREP_WATCH': '0'}):
            self.assertIsNone(W.tick(a))
            W.arm(a)
        self.assertIsNone(getattr(a, '_view_prep_watch_job', None))

    def test_one_watch_at_a_time(self):
        a = self.a
        W.arm(a)
        first = a._view_prep_watch_job
        W.arm(a)
        self.assertEqual(a._view_prep_watch_job, first)
        self.root.after_cancel(first)
        before = len(self.root.tk.splitlist(self.root.tk.call('after', 'info')))
        W.tick(a)                                    # 小分けを予約し直し（見張りも1つ立つ）、自分では二重に立てない
        after = len(self.root.tk.splitlist(self.root.tk.call('after', 'info')))
        self.assertEqual(a.scheduled, 1)
        self.assertEqual(after - before, 2)          # 小分け1つ・見張り1つ


if __name__ == '__main__':
    unittest.main()
