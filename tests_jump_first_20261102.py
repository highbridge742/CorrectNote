# -*- coding: utf-8 -*-
"""解析の途中で飛んだ先を、計算中の行があっても先に回す（app._reprioritise_visible・2026-11-02）。

答えが届いた区切りの中で次の行を送るので、見るときはいつも計算中で、計算中なら並べ替えない決まりのせいで飛んだ先が
先に回らなかった（3,609行のタブの真ん中へ飛んで、30秒たっても映っている11行が0行 → 直して20秒で10行）。計算中の
行は動かさない（答えはその行の順番で受け取る）。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


def _host(pending=None, pos=0):
    host = SimpleNamespace(_analyze_todo=list(range(100)), _analyze_pos=pos, _analyze_units_only=False, _async_request=pending,
                           _prev_lines=['行'] * 100, ANALYZE_CHUNK=8, VISIBLE_SHORT_FIRST=False)
    host._visible_band = lambda margin=20: (50, 52) if margin == 0 else (45, 57)
    host.JUMP_CANCELS_ROW = True
    host.JUMP_CANCEL_MAX_S = 3.0
    host._nearest_rows_first = lambda rows, lo, hi: app.CorrectNoteApp._nearest_rows_first(host, rows, lo, hi)
    host._analyze_work = 'work'
    host._may_cancel_row = lambda row: app.CorrectNoteApp._may_cancel_row(host, row)
    host._typed_row_pending = lambda: False
    return host


class JumpFirstTests(unittest.TestCase):
    def reorder(self, host):
        with patch.object(app.analysis_async, 'cancel_foreground_request') as cancel:
            moved = app.CorrectNoteApp._reprioritise_visible(host)
        return moved, cancel.called

    def test_a_row_in_the_child_out_of_view_goes_behind_the_view(self):
        # 重い行は10秒を超えるので、やめて後ろへ回す（飛んで1秒で2行 ← 0行）
        host = _host((('line', 'work', 'state', 'text', 3, False), 7), pos=3)
        self.assertEqual(self.reorder(host), (True, True))
        self.assertEqual(host._analyze_todo[:3], [0, 1, 2])
        self.assertEqual(host._analyze_todo[3:6], [50, 51, 52])       # 映っている行が先
        self.assertEqual(host._analyze_todo[6:11], [45, 46, 47, 48, 49])
        self.assertIn(3, host._analyze_todo[6:])                      # やめた行は後ろに残る
        self.assertEqual(sorted(host._analyze_todo), list(range(100)))
        self.assertEqual((host._analyze_painted_pos, host._analyze_visible_n), (3, 6))

    def test_the_typed_row_stays_in_the_child(self):
        host = _host((('line', 'work', 'state', 'text', 3, False), 7), pos=3)
        host._typed_row_pending = lambda: True
        self.assertEqual(self.reorder(host), (True, False))
        self.assertEqual(host._analyze_todo[:7], [0, 1, 2, 3, 50, 51, 52])
        self.assertEqual((host._analyze_painted_pos, host._analyze_visible_n), (3, 7))

    def test_a_row_in_the_child_in_view_stays(self):
        host = _host((('line', 'work', 'state', 'text', 46, False), 7), pos=46)
        host._analyze_todo = [46] + [i for i in range(100) if i != 46]; host._analyze_pos = 0
        self.assertEqual(self.reorder(host), (True, False))
        self.assertEqual(host._analyze_todo[:4], [46, 50, 51, 52])

    def test_after_the_view_the_nearest_rows_and_below_first(self):
        host = _host()
        order = app.CorrectNoteApp._nearest_rows_first(host, [0, 40, 44, 58, 60, 99], 45, 57)
        self.assertEqual(order, [58, 44, 60, 40, 99, 0])

    def test_cancelling_has_limits(self):
        # 捨てる計算を増やさない: 同じ行は1回まで、計算を始めて数秒たった行は終わらせる
        host = _host()
        may = app.CorrectNoteApp._may_cancel_row
        self.assertTrue(may(host, 3))
        self.assertFalse(may(host, 3))
        self.assertTrue(may(host, 4))
        host._analyze_work = 'other pass'
        self.assertTrue(may(host, 3))
        host._async_request_at = app.time.monotonic() - 3.1
        self.assertFalse(may(host, 5))

    def test_without_a_row_in_the_child_it_starts_at_the_position(self):
        host = _host(None, pos=3)
        self.assertTrue(app.CorrectNoteApp._reprioritise_visible(host))
        self.assertEqual(host._analyze_todo[3:6], [50, 51, 52])

    def test_the_next_row_already_in_view_changes_nothing(self):
        host = _host((('line', 'work', 'state', 'text', 49, False), 7), pos=49)
        self.assertFalse(app.CorrectNoteApp._reprioritise_visible(host))
        self.assertEqual(host._analyze_todo, list(range(100)))


if __name__ == '__main__':
    unittest.main()
