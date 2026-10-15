# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Memory modes change retention, never a correction request or model state."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import analysis_async as A
import analysis_worker as W
import memory_usage as M
import quick_analysis as Q
from settings import Settings, MEMORY_HIGH, MEMORY_LOW, MEMORY_MID


class Timers:
    def __init__(self):
        self.serial = 0
        self.calls = {}
        self.cancelled = []

    def after(self, delay, callback):
        self.serial += 1
        name = 'job-' + str(self.serial)
        self.calls[name] = (delay, callback)
        return name

    def after_cancel(self, name):
        self.cancelled.append(name)

    def run(self, name):
        self.calls[name][1]()


def owner(mode=MEMORY_LOW):
    worker = SimpleNamespace(process=Mock(), close=Mock(), submit=Mock(), poll=Mock())
    worker.process.is_alive.return_value = True
    worker.submit.return_value = 9
    app = SimpleNamespace(root=Timers(), settings=Settings(), status=Mock(),
        _correction_worker=worker, _worker_state=('old',),
        _foreground_analysis_pending=Mock(return_value=False))
    app.settings.set('memory_usage', mode)
    return app, worker


class MemorySettingsTests(unittest.TestCase):
    def test_default_and_invalid_saved_values_use_high(self):
        self.assertEqual(Settings().get('memory_usage'), MEMORY_HIGH)
        with tempfile.TemporaryDirectory(dir=Path(__file__).absolute().parent) as directory:
            path = Path(directory) / 'synthetic_settings.json'
            for value in ('unknown', None, True, 1, [], {}):
                with self.subTest(value=value):
                    path.write_text(json.dumps({'memory_usage': value}), encoding='utf8')
                    self.assertEqual(Settings(str(path)).get('memory_usage'), MEMORY_HIGH)

    def test_low_and_high_save_and_reload_without_other_setting_changes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).absolute().parent) as directory:
            path = str(Path(directory) / 'synthetic_settings.json')
            settings = Settings(path)
            settings.set('input_method', 'kana')
            settings.set('theme', 'dark')   # dark_mode は配色から決まる（外見）
            for mode in (MEMORY_LOW, MEMORY_HIGH):
                settings.set('memory_usage', mode)
                settings.save()
                loaded = Settings(path)
                self.assertEqual(loaded.get('memory_usage'), mode)
                self.assertEqual(loaded.get('input_method'), 'kana')
                self.assertTrue(loaded.get('dark_mode'))


class MemoryWorkerRetentionTests(unittest.TestCase):
    def test_low_releases_idle_child_and_invalidates_only_its_snapshot(self):
        app, worker = owner()
        app.line_results = [{'original': '資料', 'corrected': '資料', 'analysis_status': 'complete'}]
        app._units_cache = {('資料', '資料'): ('資料', [])}
        previous = W.state_key(app)
        M.queue_release(app, 'foreground')
        name = app._memory_foreground_job
        self.assertEqual(app.root.calls[name][0], 5000)
        worker.close.assert_not_called()
        app.root.run(name)
        worker.close.assert_called_once()
        self.assertIsNone(app._correction_worker)
        self.assertIsNone(app._worker_state)
        self.assertEqual(app.line_results[0]['analysis_status'], 'complete')
        self.assertEqual(app._units_cache, {('資料', '資料'): ('資料', [])})
        self.assertEqual(W.state_key(app), previous)

    def test_inflight_or_unapplied_foreground_values_are_retained(self):
        for name, value in (('_async_request', ('row', 9)),
                            ('_async_context_scope', ('prepare', 2))):
            with self.subTest(name=name):
                app, worker = owner()
                M.queue_release(app, 'foreground')
                setattr(app, name, value)
                app.root.run(app._memory_foreground_job)
                worker.close.assert_not_called()
                self.assertIsNotNone(app._memory_foreground_job)
        app, worker = owner()
        M.queue_release(app, 'foreground')
        app._foreground_analysis_pending.return_value = True
        app.root.run(app._memory_foreground_job)
        worker.close.assert_not_called()
        app._foreground_analysis_pending.return_value = False
        app.root.run(app._memory_foreground_job)
        worker.close.assert_called_once()

    def test_unapplied_quick_value_timers_and_f2_are_retained(self):
        for name, value in (('_quick_job', {'value': {'results': []}}),
                            ('_quick_after_id', 'display'),
                            ('_quick_prepare_after_id', 'prepare'),
                            ('_quick_f2_pending', ('scope', '1.0'))):
            with self.subTest(name=name):
                app, worker = owner()
                app._quick_worker = worker
                app._quick_worker_state = ('old',)
                M.queue_release(app, 'quick')
                setattr(app, name, value)
                app.root.run(app._memory_quick_job)
                worker.close.assert_not_called()
                setattr(app, name, None)
                app.root.run(app._memory_quick_job)
                worker.close.assert_called_once()
                self.assertIsNone(app._quick_worker_state)
                self.assertFalse(app._quick_composition_prepared)

    def test_latest_timer_owns_even_the_same_retained_worker(self):
        app, worker = owner()
        M.queue_release(app, 'foreground')
        first = app._memory_foreground_job
        M.queue_release(app, 'foreground')
        second = app._memory_foreground_job
        self.assertIn(first, app.root.cancelled)
        app.root.run(first)
        worker.close.assert_not_called()
        self.assertEqual(app._memory_foreground_job, second)
        app.root.run(second)
        worker.close.assert_called_once()

    def test_replaced_worker_and_closing_owner_make_timer_inert(self):
        app, worker = owner()
        M.queue_release(app, 'foreground')
        name = app._memory_foreground_job
        app._correction_worker = Mock()
        app.root.run(name)
        worker.close.assert_not_called()
        app._correction_worker.close.assert_not_called()
        app, worker = owner()
        M.queue_release(app, 'foreground')
        name = app._memory_foreground_job
        app._closing = True
        app.root.run(name)
        worker.close.assert_not_called()

    def test_new_request_cancels_expiry_and_keeps_the_same_snapshot(self):
        app, worker = owner()
        app._worker_state = W.state_key(app)
        M.queue_release(app, 'foreground')
        name = app._memory_foreground_job
        with patch.object(A, 'snapshot', side_effect=AssertionError('same model')):
            A._request(app, {'kind': 'prepare', 'lines': ['資料']}, ('current',))
        app.root.run(name)
        worker.close.assert_not_called()
        worker.submit.assert_called_once_with({'kind': 'prepare', 'lines': ['資料']}, None)
        self.assertEqual(app._async_request, (('current',), 9))

    def test_next_request_after_release_gets_full_latest_snapshot(self):
        app, old = owner()
        M.queue_release(app, 'foreground')
        app.root.run(app._memory_foreground_job)
        app._analysis_state_revision = 3
        new = Mock()
        new.submit.return_value = 11
        with patch.object(A, 'Worker', return_value=new), patch.object(A, 'snapshot', return_value={'latest': 3}) as snap:
            A._request(app, {'kind': 'prepare', 'lines': ['新しい資料']}, ('new',))
        snap.assert_called_once_with(app)
        self.assertEqual(new.submit.call_args[0][1]['latest'], 3)
        self.assertEqual(new.submit.call_args[0][1]['_state_identity'], W.state_key(app))
        self.assertIs(app._correction_worker, new)

    def test_high_and_switch_back_cancel_expiry_without_changing_results(self):
        app, worker = owner(MEMORY_HIGH)
        M.queue_release(app, 'foreground')
        self.assertEqual(app.root.calls, {})
        app.settings.set('memory_usage', MEMORY_LOW)
        M.queue_release(app, 'foreground')
        name = app._memory_foreground_job
        app.settings.set('memory_usage', MEMORY_HIGH)
        M.cancel_releases(app)
        app.root.run(name)
        worker.close.assert_not_called()
        self.assertIs(app._correction_worker, worker)

    def test_close_cancels_release_before_closing_and_late_callback_is_inert(self):
        app, worker = owner()
        M.queue_release(app, 'foreground')
        name = app._memory_foreground_job
        A.close(app, keep_prewarmed=True)
        worker.close.assert_called_once()
        app.root.run(name)
        worker.close.assert_called_once()
        self.assertIsNone(app._correction_worker)

    def test_close_disposes_both_channels_and_cancels_all_expiry(self):
        app, foreground = owner()
        quick = Mock()
        app._quick_worker = quick
        app._quick_worker_state = ('quick model',)
        M.queue_release(app, 'foreground')
        M.queue_release(app, 'quick')
        foreground_timer = app._memory_foreground_job
        quick_timer = app._memory_quick_job
        A.close(app)
        foreground.close.assert_called_once()
        quick.close.assert_called_once()
        self.assertIsNone(app._memory_foreground_job)
        self.assertIsNone(app._memory_quick_job)
        app.root.run(foreground_timer)
        app.root.run(quick_timer)
        quick.close.assert_called_once()
        self.assertIsNone(app._quick_worker)

    def test_low_skips_optional_public_preparation_without_snapshot(self):
        app, worker = owner()
        app._correction_worker = None
        with patch.object(A, 'Worker', side_effect=AssertionError('no preload')), patch.object(A, 'snapshot', side_effect=AssertionError('no state')):
            A.prewarm(app)
            A.queue_idle_prewarm(app)
        self.assertEqual(app.root.calls, {})

    def test_switch_low_parks_background_first_and_releases_only_optional_work(self):
        import os
        import compact_tables
        from app import CorrectNoteApp
        saved = os.environ.get(compact_tables.ENV)
        # _choose_memory_usage exports the table form into this process; put it back
        self.addCleanup(lambda: os.environ.pop(compact_tables.ENV, None) if saved is None
                        else os.environ.__setitem__(compact_tables.ENV, saved))
        app, worker = owner(MEMORY_HIGH)
        app.memory_usage_var = SimpleNamespace(get=lambda: MEMORY_LOW)
        app.settings.save = Mock()
        prefetched = Mock()
        app._prefetch_worker = prefetched
        app._async_request = ('foreground', 9)
        app._quick_worker = Mock()
        app._quick_job = {'value': None}
        app._stop_background_tabs = Mock(side_effect=lambda: self.assertEqual(app.settings.get('memory_usage'), MEMORY_LOW))
        CorrectNoteApp._choose_memory_usage(app)
        app._stop_background_tabs.assert_called_once()
        prefetched.close.assert_called_once()
        app.settings.save.assert_called_once()
        app.root.run(app._memory_foreground_job)
        app.root.run(app._memory_quick_job)
        worker.close.assert_not_called()
        app._quick_worker.close.assert_not_called()
        CorrectNoteApp._queue_background_tabs(app)
        CorrectNoteApp._start_background_tabs(app)
        self.assertFalse(hasattr(app, '_bg_start_job'))


class MemoryQuickTests(unittest.TestCase):
    def make(self):
        from tests_quick_async import Widget
        app, worker = owner()
        app._quick_text = Widget('橋')
        app._quick_worker = None
        app._analyze_quick = Mock()
        app._finish_quick_analysis = Mock(return_value=False)
        app._autofix_live_records = Mock(return_value=[])
        app._on_quick_f2 = Mock()
        worker.poll.return_value = None
        worker.submit.side_effect = range(1, 20)
        return app, worker

    def test_low_composition_waits_for_commit_then_keeps_reading_and_f2(self):
        import analysis_work_app as work
        app, worker = self.make()
        with patch.object(Q, 'Worker', return_value=worker) as create, patch.object(Q, 'snapshot', return_value={'state': 'latest'}), patch.object(Q, '_composing', return_value=True) as composing:
            Q.schedule_prepare(app)
            Q.prepare(app)
            Q.start(app)
            create.assert_not_called()
            self.assertIsNone(app._quick_worker)
            app._quick_after_id = None
            doc = work.quick_document(app, '橋')
            self.assertTrue(doc.remember(0, 1, '橋', 'はし'))
            Q.defer_f2(app)
            composing.return_value = False
            Q.start(app)
            task = worker.submit.call_args[0][0]
            self.assertEqual(task['kind'], 'quick')
            self.assertEqual(task['readings'][0], doc.occurrences)
            app._on_quick_f2.assert_not_called()
            worker.poll.return_value = dict(results=[{'original': '橋', 'corrected': '橋', 'analysis_status': 'complete'}], units=[[]], corrected_units=[('橋', [])])
            app._quick_after_id = None
            Q.start(app)
            app._finish_quick_analysis.assert_called_once()
            app._on_quick_f2.assert_called_once()
            app.root.run(app._memory_quick_job)
            worker.close.assert_called_once()
            self.assertIsNone(app._quick_worker)

    def test_low_window_close_does_not_keep_an_idle_child(self):
        app, worker = self.make()
        app._quick_worker = worker
        app._quick_worker_state = ('old',)
        Q.close(app, keep_idle_worker=True)
        worker.close.assert_called_once()
        self.assertIsNone(app._quick_worker)
        self.assertIsNone(app._quick_worker_state)


class MemoryTierTests(unittest.TestCase):
    """2026-10-14 うにさん: low/mid/high with upper limits 700/1400/2100MB;
    default high, a saved choice is kept as it is."""
    def test_three_tiers_default_high_and_saved_choices_kept(self):
        from settings import MEMORY_MID, MEMORY_CHOICES
        self.assertEqual(MEMORY_CHOICES, (MEMORY_LOW, MEMORY_MID, MEMORY_HIGH))
        self.assertEqual(Settings().get('memory_usage'), MEMORY_HIGH)
        with tempfile.TemporaryDirectory(dir=Path(__file__).absolute().parent) as directory:
            path = Path(directory) / 'synthetic_settings.json'
            for value in (MEMORY_LOW, MEMORY_MID, MEMORY_HIGH):
                path.write_text(json.dumps({'memory_usage': value}), encoding='utf8')
                self.assertEqual(Settings(str(path)).get('memory_usage'), value)

    def test_saving_and_compact_by_tier(self):
        # 2026-10-15 うにさん「中は高に寄せた処理で1500前後に」: 中は表のタブの
        # 子を残して温め、本体も表を先読みし、裏のタブは同じ子で進める。
        # 簡易入力の子は閉じる。低だけが小さな表で、何も残さない。
        from settings import MEMORY_MID
        for value, expect in (
                (MEMORY_LOW, dict(low=True, compact=True, fg=False, quick=False, shared=False,
                                  prefetch=False, background=False, prewarm=False, preload=False, qprep=False)),
                (MEMORY_MID, dict(low=False, compact=False, fg=True, quick=False, shared=True,
                                  prefetch=False, background=True, prewarm=True, preload=True, qprep=False)),
                (MEMORY_HIGH, dict(low=False, compact=False, fg=True, quick=True, shared=False,
                                   prefetch=True, background=True, prewarm=True, preload=True, qprep=True))):
            app, _ = owner(value)
            got = dict(low=M.low(app), compact=M.compact(app), fg=M.retains(app, 'foreground'),
                       quick=M.retains(app, 'quick'), shared=M.shares_worker(app),
                       prefetch=M.prefetch_worker(app), background=M.background_tabs(app),
                       prewarm=M.prewarm(app), preload=M.preloads(app), qprep=M.quick_prepare(app))
            self.assertEqual(got, expect, value)
        app, _ = owner(MEMORY_HIGH)
        app.settings.set('memory_usage', 'unknown')
        self.assertEqual(M.mode(app), MEMORY_HIGH)

    def test_cache_sizes_by_tier(self):
        from settings import MEMORY_MID
        for value, tabs, cache, units, contexts in (
                (MEMORY_LOW, 20, 1, 0, 4), (MEMORY_MID, 20, 12, 3, 4),
                (MEMORY_HIGH, 20, 20, 20, 20), (MEMORY_HIGH, 2, 12, 3, 4)):
            app, _ = owner(value)
            app.session = SimpleNamespace(tabs=[object()] * tabs)
            self.assertEqual((M.cache_tabs(app, 12), M.units_cache_tabs(app), M.context_cache_size(app)),
                             (cache, units, contexts), value)
        self.assertEqual((M.completed_tabs(owner(MEMORY_LOW)[0]), M.completed_tabs(owner(MEMORY_MID)[0]),
                          M.completed_tabs(owner(MEMORY_HIGH)[0])), (1, None, None))

    def test_low_keeps_completed_values_for_the_open_tab_only(self):
        import tab_analysis as T
        import analysis_work_app as work
        for value, kept in ((MEMORY_LOW, 1), (MEMORY_MID, 3), (MEMORY_HIGH, 3)):
            with self.subTest(value=value):
                app, _ = owner(value)
                owners = [object(), object(), object()]
                app.session = SimpleNamespace(tabs=[{'text': 'a'}, {'text': 'b'}, {'text': 'c'}])
                app._completed_tabs = {}
                with patch.object(work, 'owner_for_tab', side_effect=lambda app, tab: owners['abc'.index(tab['text'])]):
                    dependencies = W.state_key(app)
                    for tab_owner, text in zip(owners, 'abc'):
                        result = {'original': text, 'corrected': text, 'analysis_status': 'complete'}
                        self.assertTrue(T._save(app, tab_owner, text, [result], {}, {(text, text): (text, [])},
                                                {(text, text, False): (text, [])}, dependencies, ()))
                self.assertEqual(len(app._completed_tabs), kept)
                self.assertIn(owners[-1], app._completed_tabs)

    def test_mid_keeps_the_open_tabs_child_and_releases_quick(self):
        from settings import MEMORY_MID
        app, worker = owner(MEMORY_MID)
        M.queue_release(app, 'foreground')
        self.assertEqual(app.root.calls, {})
        self.assertIs(app._correction_worker, worker)
        quick = Mock()
        app._quick_worker = quick
        app._quick_worker_state = ('quick model',)
        M.queue_release(app, 'quick')
        app.root.run(app._memory_quick_job)
        quick.close.assert_called_once()
        self.assertIsNone(app._quick_worker)
        self.assertIs(app._correction_worker, worker)

    def test_mid_background_shares_the_open_tabs_child(self):
        from settings import MEMORY_MID
        app, worker = owner(MEMORY_MID)
        self.assertEqual(A._worker_fields(True, app),
                         ('_correction_worker', '_worker_state', '_async_background_request'))
        self.assertEqual(A._worker_fields(False, app), ('_correction_worker', '_worker_state', '_async_request'))
        high, _ = owner(MEMORY_HIGH)
        self.assertEqual(A._worker_fields(True, high),
                         ('_prefetch_worker', '_prefetch_worker_state', '_async_background_request'))
        self.assertEqual(A._worker_fields(True), A._worker_fields(True, high))
        # 表のタブが使っている間は、裏の求めを出さない（追い越して壊さない）
        app._worker_state = W.state_key(app)
        app._async_request = ('row', 9)
        with patch.object(A, 'snapshot', side_effect=AssertionError('same model')):
            self.assertIsNone(A._request(app, {'kind': 'prepare', 'lines': ['資料']}, ('bg',), background=True))
        worker.submit.assert_not_called()
        self.assertIsNone(getattr(app, '_async_background_request', None))
        # 空いたら同じ子へ、同じ状態のまま（写しは送らない）
        app._async_request = None
        with patch.object(A, 'snapshot', side_effect=AssertionError('same model')):
            A._request(app, {'kind': 'prepare', 'lines': ['資料']}, ('bg',), background=True)
        worker.submit.assert_called_once_with({'kind': 'prepare', 'lines': ['資料']}, None)
        self.assertEqual(app._async_background_request, (('bg',), 9))
        self.assertIsNone(getattr(app, '_prefetch_worker', None))

    def test_shared_background_request_superseded_by_the_open_tab_is_asked_again(self):
        from settings import MEMORY_MID
        app, worker = owner(MEMORY_MID)
        worker.serial = 12
        worker.poll.return_value = None
        app._async_background_request = (('bg',), 9)       # the open tab submitted 10..12 since
        self.assertEqual(A._poll(app, ('bg',), background=True), (False, None))
        self.assertIsNone(app._async_background_request)
        worker.poll.assert_not_called()
        # a cancel for the superseded request would interrupt the newer foreground work
        app._async_background_request = (('bg',), 9)
        A.cancel_background_request(app)
        worker.submit.assert_not_called()
        self.assertIsNone(app._async_background_request)
        # the newest request is polled and may be cancelled as before
        app._async_background_request = (('bg',), 12)
        worker.poll.return_value = {'done': True}
        self.assertEqual(A._poll(app, ('bg',), background=True), (True, {'done': True}))
        app._async_background_request = (('bg',), 12)
        A.cancel_background_request(app)
        worker.submit.assert_called_once_with({'kind': 'cancel'})

    def test_apply_tier_keeps_or_releases_per_tier(self):
        from settings import MEMORY_MID
        for value, fg_timer, quick_timer, prefetch_closed, warm in (
                (MEMORY_LOW, True, True, True, False), (MEMORY_MID, False, True, True, True),
                (MEMORY_HIGH, False, False, False, True)):
            with self.subTest(value=value):
                app, worker = owner(value)
                app._quick_worker = Mock()
                app._quick_worker_state = ('q',)
                prefetched = Mock()
                app._prefetch_worker = prefetched
                app._async_background_request = ('bg', 1)
                with patch.object(A, 'prewarm') as prewarm, patch.object(A, 'queue_idle_prewarm') as idle, \
                        patch.object(Q, 'schedule_prepare') as prepare:
                    M.apply_tier(app)
                self.assertEqual(getattr(app, '_memory_foreground_job', None) is not None, fg_timer)
                self.assertEqual(getattr(app, '_memory_quick_job', None) is not None, quick_timer)
                self.assertEqual(prefetched.close.called, prefetch_closed)
                if prefetch_closed:
                    self.assertIsNone(app._prefetch_worker)
                    self.assertIsNone(app._async_background_request)
                else:
                    self.assertIs(app._prefetch_worker, prefetched)
                self.assertEqual(prewarm.called, warm)
                self.assertEqual(idle.called, warm)
                self.assertEqual(prepare.called, value == MEMORY_HIGH)
                worker.close.assert_not_called()

    def test_env_tells_new_workers_the_table_form(self):
        import os
        import compact_tables
        from settings import MEMORY_MID
        saved = os.environ.get(compact_tables.ENV)
        try:
            for value, expected in ((MEMORY_LOW, '1'), (MEMORY_MID, None), (MEMORY_HIGH, None)):
                app, _ = owner(value)
                M.export_env(app)
                self.assertEqual(os.environ.get(compact_tables.ENV), expected, value)
                self.assertEqual(compact_tables.enabled(), expected == '1')
        finally:
            if saved is None:
                os.environ.pop(compact_tables.ENV, None)
            else:
                os.environ[compact_tables.ENV] = saved

    def test_tier_change_into_or_out_of_low_replaces_idle_workers(self):
        import os
        import compact_tables
        from settings import MEMORY_MID
        saved = os.environ.get(compact_tables.ENV)
        try:
            app, worker = owner(MEMORY_MID)
            M.switch_tables(app, MEMORY_HIGH)       # mid <- high: same form, kept
            worker.close.assert_not_called()
            app.settings.set('memory_usage', MEMORY_LOW)
            app._async_request = ('busy', 1)        # a busy worker finishes first
            M.switch_tables(app, MEMORY_MID)
            worker.close.assert_not_called()
            app._async_request = None
            M.switch_tables(app, MEMORY_MID)        # low <- mid: idle worker goes
            worker.close.assert_called_once_with()
            self.assertIsNone(app._correction_worker)
            self.assertEqual(os.environ.get(compact_tables.ENV), '1')
        finally:
            if saved is None:
                os.environ.pop(compact_tables.ENV, None)
            else:
                os.environ[compact_tables.ENV] = saved


class MemoryPreloadTests(unittest.TestCase):
    """2026-10-14 うにさん「低にしているのに約1500MB」: low does not preload
    the optional public tables into the main process; they load on first use.
    2026-10-15: mid preloads them like high (「中は高に寄せた処理で」)."""
    def test_mid_preloads_like_high(self):
        from settings import MEMORY_MID
        app, _ = owner(MEMORY_MID)
        loaded, importer = self._tables()
        with importer:
            self.assertEqual(M.preload_tables(app), M.OPTIONAL_PRELOAD)
        self.assertEqual(loaded, list(M.OPTIONAL_PRELOAD))

    def _tables(self):
        loaded = []
        modules = {name: SimpleNamespace(available=lambda name=name: loaded.append(name) or True)
                   for name in M.OPTIONAL_PRELOAD}
        return loaded, patch('importlib.import_module', side_effect=lambda name: modules[name])

    def test_high_preloads_the_optional_tables(self):
        app, _ = owner(MEMORY_HIGH)
        loaded, importer = self._tables()
        with importer:
            self.assertEqual(M.preload_tables(app), M.OPTIONAL_PRELOAD)
        self.assertEqual(loaded, list(M.OPTIONAL_PRELOAD))

    def test_low_leaves_them_for_first_use(self):
        app, _ = owner(MEMORY_LOW)
        loaded, importer = self._tables()
        with importer:
            self.assertEqual(M.preload_tables(app), ())
        self.assertEqual(loaded, [])

    def test_the_tables_still_load_themselves_on_demand(self):
        import oddness
        import seed_japanese
        for module in (seed_japanese, oddness):
            self.assertTrue(callable(getattr(module, '_load', None)), module.__name__)


if __name__ == '__main__':
    unittest.main()
