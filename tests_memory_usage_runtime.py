# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""All tiers give the same outputs: real workers (high; mid with cold restarts;
low with cold restarts and compact tables, 2026-10-14)."""
import os
from types import SimpleNamespace
import unittest

import analysis_async as A
import analysis_worker as W
import memory_usage as M
from settings import MEMORY_HIGH, MEMORY_LOW, MEMORY_MID
from tests_analysis_async import initial, wait
from tests_memory_usage import Timers


class MemoryRuntimeTests(unittest.TestCase):
    def test_foreground_and_quick_all_values_match_with_optional_prewarm_or_cold_restart(self):
        app = initial()
        app.settings['input_method'] = 'romaji'
        app.root = Timers()
        app._foreground_analysis_pending = lambda: False
        lines = ['寒ぃ日だ。', 'よいでしょぅか。', '公園で歩きます。',
                 '😀書類を作成しました。', 'kouendearukisoudesu\t',
                 '橋を渡ります。', 'x = "kouendearukisoudesu"']
        values = {}
        saved_env = os.environ.get('CN_COMPACT_TABLES')
        self.addCleanup(lambda: os.environ.pop('CN_COMPACT_TABLES', None) if saved_env is None
                        else os.environ.__setitem__('CN_COMPACT_TABLES', saved_env))
        for mode in (MEMORY_HIGH, MEMORY_MID, MEMORY_LOW):
            app.settings['memory_usage'] = mode
            M.export_env(app)       # low: the worker uses compact tables
            try:
                if mode == MEMORY_HIGH:
                    A.prewarm(app)
                    wait(app._correction_worker, 1)
                scope = ('prepared', mode)
                identifier = A._request(app, dict(kind='prepare', lines=lines), scope)
                prepared = wait(app._correction_worker, identifier)
                app._async_request = None
                rows = []
                for index, line in enumerate(lines):
                    task = dict(kind='line', line=line, context=prepared['context'],
                                input_method='romaji', attested=prepared['attested'])
                    identifier = A._request(app, task, ('row', mode, index))
                    rows.append(wait(app._correction_worker, identifier))
                    app._async_request = None
                    if mode == MEMORY_LOW:
                        worker = app._correction_worker
                        M.queue_release(app, 'foreground')
                        app.root.run(app._memory_foreground_job)
                        self.assertFalse(worker.process.is_alive())
                        self.assertIsNone(app._worker_state)
                    elif mode == MEMORY_MID:
                        # 2026-10-15: mid keeps the open tab's child ready, and the
                        # other tabs' rows go to that same child (no second process).
                        worker = app._correction_worker
                        M.queue_release(app, 'foreground')
                        self.assertFalse(hasattr(app, '_memory_foreground_job') and app._memory_foreground_job)
                        self.assertTrue(worker.process.is_alive())
                        identifier = A._request(app, task, ('background row', index), background=True)
                        self.assertIs(app._correction_worker, worker)
                        self.assertIsNone(getattr(app, '_prefetch_worker', None))
                        shared = wait(worker, identifier)
                        app._async_background_request = None
                        self.assertEqual(shared, rows[-1])
                values[mode] = (prepared, rows)
            finally:
                A.close(app)
        self.assertEqual(values[MEMORY_MID], values[MEMORY_HIGH])
        self.assertEqual(values[MEMORY_LOW], values[MEMORY_HIGH])
        self.assertTrue(all(row['result']['analysis_status'] == 'complete'
                            for row in values[MEMORY_LOW][1]))

        task = dict(kind='quick', lines=['寒ぃ日だ。', '橋を渡ります。', '8*5'],
                    input_method='romaji', attested=(), readings={}, calculations={})
        outputs = {}
        for mode in (MEMORY_HIGH, MEMORY_LOW):
            app.settings['memory_usage'] = mode
            M.export_env(app)
            worker = W.Worker()     # low: compact tables (CN_COMPACT_TABLES=1)
            try:
                state = W.snapshot(app)
                if mode == MEMORY_HIGH:
                    # Wait for optional preparation separately, as during an
                    # already-open high-mode Quick window. No expected answers.
                    worker.submit(dict(kind='quick_prepare'), state)
                    identifier = worker.submit(dict(kind='warmup'))
                    wait(worker, identifier)
                    state = None
                outputs[mode] = wait(worker, worker.submit(task, state))
            finally:
                worker.close()
        self.assertEqual(outputs[MEMORY_LOW], outputs[MEMORY_HIGH])

    def test_latest_blocks_choice_and_positioned_reading_survive_real_child_release(self):
        from analysis_work import Document
        app = initial()
        app.settings['memory_usage'] = MEMORY_LOW
        app.root = Timers()
        app._foreground_analysis_pending = lambda: False
        line = '寒ぃ日だ。\t橋を渡ります。'
        doc = Document(object(), line)
        self.assertTrue(doc.remember(6, 7, '橋', 'はし'))
        task = dict(kind='line', line=line, context={}, input_method='kana',
                    attested=(), readings=doc.occurrences)
        try:
            identifier = A._request(app, task, ('first',))
            original = wait(app._correction_worker, identifier)
            app._async_request = None
            old = app._correction_worker
            M.queue_release(app, 'foreground')
            app.root.run(app._memory_foreground_job)
            self.assertFalse(old.process.is_alive())
            app.decisions.protect('寒ぃ')
            app._analysis_state_revision = 1
            identifier = A._request(app, task, ('latest',))
            changed = wait(app._correction_worker, identifier)
            self.assertIsNot(app._correction_worker, old)
            self.assertEqual(changed['result']['corrected'], line)
            self.assertEqual(changed['result']['original'], original['result']['original'])
            self.assertEqual(changed['result']['analysis_status'], 'complete')
            self.assertNotEqual(changed['result']['corrected'], original['result']['corrected'])
        finally:
            A.close(app)


if __name__ == '__main__':
    unittest.main()
