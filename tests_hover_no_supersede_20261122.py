# -*- coding: utf-8 -*-
"""オンマウスの一覧の頼みで、子が解いている本体の行を捨てさせない（2026-11-22 19:49 JST うにさん「いま解析が進んでいないように
見える」）。子は新しい頼みが来ると解いている頼みを捨てる（analysis_worker._serve_requests）ので、本体の行の答えが来ないまま
解析が止まっていた。本体の頼みが子にある間は頼まず（_Busy）、行と行の間（子が空いている）に本体で待つ形で出す。
CN_HOVER_ASK_NO_SUPERSEDE=0 で前の形。Tk の窓は作らない（作り物のアプリと子）。"""
import os
import time
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC
import analysis_async


class FakeWorker:
    def __init__(self):
        import queue
        self.outbox = queue.Queue()
        self.ready = {}
        self.partials = {}
        self.closed = False
        self.process = NS(is_alive=lambda: True)
        self.submitted = []
        self.serial = 10

    def submit(self, task, state=None):
        self.serial += 1
        self.submitted.append((self.serial, task))
        return self.serial

    def poll(self, request_id):
        return None


def fake_app(worker, **extra):
    app = NS(_correction_worker=worker, _worker_state='S',
             _hover_asks=dict(key='k', pending={}, got={}, done={}, since=time.monotonic()))
    for k, v in extra.items():
        setattr(app, k, v)
    return app


TASK = dict(kind='candidates', surface='会議', reading='かいぎ', options={})


class NoSupersede(unittest.TestCase):
    def ask(self, app):
        with mock.patch.object(analysis_async, 'state_key', lambda a: 'S'):
            AC._hover_ask(app)(app, TASK)

    def test_not_while_the_main_row_is_with_the_child(self):
        worker = FakeWorker()
        app = fake_app(worker, _async_request=(('line', 1, 2, 3, 4, False), 7))
        with self.assertRaises(AC._Busy):
            self.ask(app)
        self.assertEqual(worker.submitted, [])                  # 本体の行を捨てさせる頼みは出さない

    def test_background_row_on_the_same_child(self):
        worker = FakeWorker()
        app = fake_app(worker, _async_request=None, _async_background_request=('x', 3))
        import memory_usage
        with mock.patch.object(memory_usage, 'shares_worker', lambda a: True):
            with self.assertRaises(AC._Busy):
                self.ask(app)
        with mock.patch.object(memory_usage, 'shares_worker', lambda a: False):
            with self.assertRaises(AC._Deferred):                # 裏のタブは別の子: 頼んでよい
                self.ask(app)

    def test_free_child_is_asked(self):
        worker = FakeWorker()
        app = fake_app(worker, _async_request=None)
        with self.assertRaises(AC._Deferred):
            self.ask(app)
        self.assertEqual(len(worker.submitted), 1)

    def test_switch_back(self):
        worker = FakeWorker()
        app = fake_app(worker, _async_request=(('line',), 7))
        with mock.patch.dict(os.environ, {'CN_HOVER_ASK_NO_SUPERSEDE': '0'}):
            with self.assertRaises(AC._Deferred):
                self.ask(app)
        self.assertEqual(len(worker.submitted), 1)               # 前の形: 本体の行が子にあっても頼んでいた

    def test_between_rows_asks_with_waiting(self):
        # 行と行の間（run_waiting_hover）は待たない頼みにしない（すぐ後の本体の行の頼みに捨てられるため）
        seen = {}

        def fake_show(app, widget, key, snap, between_rows=False, idle_child=False):
            seen.update(between_rows=between_rows, idle_child=idle_child)
            return True
        app = NS(_hover_waiting=('w', 'k', dict(busy_since=time.monotonic())), _async_request=None)
        with mock.patch.object(AC, 'hover_show', fake_show):
            self.assertTrue(AC.run_waiting_hover(app))
        self.assertEqual(seen, dict(between_rows=True, idle_child=True))

    def test_timeout_waits_for_the_next_gap(self):
        worker = FakeWorker()
        app = fake_app(worker, _async_request=None)
        app._hover_asks['pending'] = {'t': 99}
        app._hover_asks['since'] = time.monotonic() - AC.HOVER_ASK_TIMEOUT_S - 1
        calls = []
        with mock.patch.object(AC, '_retry_later', lambda *a: calls.append(a[2])):
            AC._poll_asks(app, 'w', 'k', {})
        self.assertIsNone(app._hover_asks)
        self.assertEqual(calls, ['k'])                           # 行と行の間に出し直す


if __name__ == '__main__':
    unittest.main()
