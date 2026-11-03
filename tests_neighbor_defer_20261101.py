# -*- coding: utf-8 -*-
"""打っている間、打った行の上下の行（文脈の近傍）の解析し直しを入力が止まるまで待つ（app._defer_neighbor_rows・
2026-11-01・処理の負荷）。打鍵ごとに上下4行の解析し直しが走り、次の打鍵で捨てられていた（1字ごとに5行 → 1行）。
止まったら解析し直す（答えは同じ: 写しで6打鍵の後の全部の行の答えが一致）。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


class _Root:
    def __init__(self):
        self.jobs = []

    def after(self, ms, fn):
        self.jobs.append((ms, fn))
        return len(self.jobs)

    def after_cancel(self, job):
        pass


def _host(typed=True):
    host = SimpleNamespace(root=_Root(), _priority_input_row=(('tab', 1), 0) if typed else None,
                           _deferred_neighbors=set(), _closing=False)
    host.NEIGHBOR_DEFER, host.NEIGHBOR_DEFER_MS = True, 1200
    host._flush_deferred_neighbors = lambda: None
    return host


class NeighborDeferTests(unittest.TestCase):
    def defer(self, host, affected, lines, prev, head, tail):
        with patch.object(app.input_work, 'token', lambda a: ('tab', 1)):
            return app.CorrectNoteApp._defer_neighbor_rows(host, affected, lines, prev, head, tail)

    def test_typing_keeps_the_neighbours_and_moves_them_with_the_text(self):
        prev = ['行%d' % i for i in range(10)]
        lines = list(prev); lines[5] = '行5あ'
        host = _host()
        affected = [3, 4, 6, 7]
        self.assertEqual(self.defer(host, affected, lines, prev, 5, 4), {3, 4, 6, 7})
        self.assertEqual(host.root.jobs[-1][0], 1200)
        # 次の打鍵で改行が入って行がずれても、待たせた行は付いていく
        prev2 = list(lines); lines2 = lines[:5] + ['行5あ', 'い'] + lines[6:]
        got = self.defer(host, [3, 4, 7, 8], lines2, prev2, 5, 4)
        self.assertEqual(got, {3, 4, 7, 8})
        self.assertIn((7, '行6'), host._deferred_neighbors)

    def test_a_pause_or_another_edit_hands_them_back(self):
        prev = ['行%d' % i for i in range(10)]
        lines = list(prev); lines[5] = '行5あ'
        host = _host()
        self.defer(host, [3, 4, 6, 7], lines, prev, 5, 4)
        host._neighbor_force = True                      # 止まった（_flush_deferred_neighbors）
        affected = []
        self.assertEqual(self.defer(host, affected, lines, lines, 10, 0), set())
        self.assertEqual(sorted(affected), [3, 4, 6, 7])  # この段取りで解析し直す
        self.assertEqual(host._deferred_neighbors, set())

    def test_switched_off(self):
        prev = ['行%d' % i for i in range(10)]
        lines = list(prev); lines[5] = '行5あ'
        host = _host(); host.NEIGHBOR_DEFER = False
        self.assertEqual(self.defer(host, [3, 4, 6, 7], lines, prev, 5, 4), set())


if __name__ == '__main__':
    unittest.main()
