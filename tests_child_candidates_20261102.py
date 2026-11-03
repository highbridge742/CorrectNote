# -*- coding: utf-8 -*-
"""再変換の候補づくりを解析の子で（analysis_async.ask_child・2026-11-02 うにさん「解析のメモリと再変換のメモリが同時に
掛からないこと」）。子が持っている表で作るので、本体は最初の F5 で表を読まない（本体 +146MB → +6MB・2.2秒 → 0.6秒）。
子がいない・準備の最中なら、今までどおり本体で作る。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_async as A


class _Worker:
    closed = False

    def __init__(self, answers=()):
        self.answers = list(answers); self.tasks = []
        self.process = SimpleNamespace(is_alive=lambda: True)
        self.serial = 0

    def submit(self, task, state=None):
        self.tasks.append(task); self.serial += 1
        return self.serial

    def poll(self, identifier):
        return self.answers.pop(0) if self.answers else None


def _app(worker=None, pending=None):
    return SimpleNamespace(_correction_worker=worker, _worker_state='ready', _async_request=pending, _closing=False)


class AskChildTests(unittest.TestCase):
    def ask(self, app, task=None):
        with patch.object(A, 'state_key', lambda a: 'ready'), patch.object(A.memory_usage, 'queue_release', lambda *a: None), \
                patch.object(A.memory_usage, 'cancel_release', lambda *a: None):
            return A.ask_child(app, task or dict(kind='synonyms', text='語'))

    def test_the_answer_comes_from_the_child(self):
        worker = _Worker([None, [['類語']]])
        app = _app(worker)
        self.assertEqual(self.ask(app), [['類語']])
        self.assertEqual(worker.tasks, [dict(kind='synonyms', text='語')])
        self.assertIsNone(app._async_request)            # 次の解析の区切りが行を送り直す

    def test_a_row_in_the_child_gives_way_and_is_asked_again(self):
        worker = _Worker([[]])
        app = _app(worker, (('line', 'work', 'state', 'text', 3, False), 1))
        self.assertEqual(self.ask(app), [])
        self.assertEqual(worker.tasks[0]['kind'], 'cancel')
        self.assertIsNone(app._async_request)

    def test_a_child_given_back_is_started_again(self):
        started = []
        def request(app, task, scope, **k):
            app._correction_worker = SimpleNamespace(process=SimpleNamespace(is_alive=lambda: True), poll=lambda i: ['answer'], closed=False)
            started.append(task['kind'])
            return 1
        app = SimpleNamespace(_correction_worker=None, _async_request=None, _closing=False)
        with patch.object(A, '_request', request), patch.object(A.memory_usage, 'queue_release'):
            self.assertEqual(A.ask_child(app, dict(kind='candidates')), ['answer'])
        self.assertEqual(started, ['candidates'])

    def test_not_started_while_closing(self):
        app = SimpleNamespace(_correction_worker=None, _async_request=None, _closing=True)
        self.assertIsNone(A.ask_child(app, dict(kind='candidates')))

    def test_otherwise_the_main_process_works_it_out(self):
        with patch.object(A, 'CHILD_CANDIDATES_SPAWN', False):
            self.assertIsNone(self.ask(_app(None)))      # 子がいない
        worker = _Worker([[]])
        self.assertIsNone(self.ask(_app(worker, (('speculate', 'work'), 1))))   # 準備の答えを待っている
        self.assertEqual(worker.tasks, [])
        dead = _Worker(); dead.process = SimpleNamespace(is_alive=lambda: False)
        self.assertIsNone(self.ask(_app(dead)))
        with patch.object(A, 'CHILD_CANDIDATES', False):
            self.assertIsNone(self.ask(_app(_Worker([[]]))))

    def test_a_preparation_gives_way_and_is_asked_again(self):
        later = []
        app = _app(_Worker([['答え']]), (('prepare', 'work'), 1))
        app._async_context_scope = 'scope'
        app._analyze_if_changed = lambda: None
        app.root = SimpleNamespace(after=lambda ms, fn: later.append(fn))
        self.assertIsNotNone(self.ask(app))
        self.assertIsNone(app._async_context_scope)
        self.assertEqual(later, [app._analyze_if_changed])

    def test_a_silent_child_does_not_hold_the_window(self):
        app = _app(_Worker())
        with patch.object(A, 'CHILD_CANDIDATES_WAIT_S', 0.02):
            self.assertIsNone(self.ask(app))
        self.assertIsNone(app._async_request)


if __name__ == '__main__':
    unittest.main()
