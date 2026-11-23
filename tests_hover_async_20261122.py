# -*- coding: utf-8 -*-
"""オンマウスの一覧は、子への頼みを待たずに出し（答えが来たら組み立てを続ける）、最後の打鍵から1秒たつまでは作らない
（2026-11-22 うにさん「オンマウスしても候補が出ません」・一覧を作る1回の本体の約 300ms のうち約 250ms は子の答えを待つ所だった）。
CN_HOVER_ASYNC=0・CN_HOVER_TYPED_QUIET=0 で前の形。Tk の窓は作らない（作り物のアプリと子）。"""
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
        value = self.ready.pop(request_id, None)
        self.ready = {k: v for k, v in self.ready.items() if k >= request_id}      # 本物と同じ片付け
        return value[0] if value else None


def fake_app(worker):
    return NS(_correction_worker=worker, _worker_state='S', _hover_asks=dict(key='k', pending={}, got={}, done={},
                                                                             since=time.monotonic()))


class TypedQuiet(unittest.TestCase):
    def test_not_right_after_typing(self):
        app = NS(_last_edit_at=time.monotonic(), _auto_key_at=0.0)
        self.assertTrue(AC.hover_typed_recently(app))
        app = NS(_last_edit_at=time.monotonic() - 2, _auto_key_at=time.monotonic() - 2)
        self.assertFalse(AC.hover_typed_recently(app))
        with mock.patch.dict(os.environ, {'CN_HOVER_TYPED_QUIET': '0'}):
            self.assertFalse(AC.hover_typed_recently(NS(_last_edit_at=time.monotonic(), _auto_key_at=0.0)))


class AsyncAsk(unittest.TestCase):
    def test_ask_does_not_wait_and_answer_survives_the_cleanup(self):
        worker = FakeWorker()
        app = fake_app(worker)
        ask = AC._hover_ask(app)
        task = dict(kind='candidates', surface='会議', reading='かいぎ', options={})
        with mock.patch.object(analysis_async, 'state_key', lambda a: 'S'):
            t = time.perf_counter()
            with self.assertRaises(AC._Deferred):
                ask(app, task)                                                       # 待たずに抜ける
            self.assertLess(time.perf_counter() - t, 0.01)
            self.assertEqual(len(worker.submitted), 1)                               # 子の列へ出した（取り消しはしない）
            rid = worker.submitted[0][0]
            worker.outbox.put((rid, ['会議', '回技'], None))                           # 子の答えが届いた
            worker.poll(rid + 5)                                                     # 本体が新しい答えを受け取る（片付け）
            self.assertEqual(ask(app, task), ['会議', '回技'])                        # 取り分けてあるので消えない
            self.assertEqual(len(worker.submitted), 1)                               # 同じ頼みを出し直さない

    def test_give_up_without_child_or_with_other_state(self):
        worker = FakeWorker()
        app = fake_app(worker)
        ask = AC._hover_ask(app)
        with mock.patch.object(analysis_async, 'state_key', lambda a: 'other'):
            with self.assertRaises(AC._GiveUp):
                ask(app, dict(kind='synonyms', text='会議'))                          # 本体で作らない
        app._correction_worker = None
        with mock.patch.object(analysis_async, 'state_key', lambda a: 'S'):
            with self.assertRaises(AC._GiveUp):
                ask(app, dict(kind='synonyms', text='会議'))

    def test_deferred_passes_through_except_exception(self):
        # 類語の段などの try/except Exception では飲み込まれない（BaseException）
        self.assertFalse(issubclass(AC._Deferred, Exception))
        self.assertFalse(issubclass(AC._GiveUp, Exception))


if __name__ == '__main__':
    unittest.main()
