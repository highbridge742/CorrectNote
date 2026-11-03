# -*- coding: utf-8 -*-
"""開いているタブの編集で、裏のタブの長い行を最初からやり直さない（2026-11-03）。"""
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import analysis_async as A


class Stop(unittest.TestCase):
    def app(self, age, scope='background', closing=False):
        return NS(_async_background_request=((scope,), 3), _async_background_request_at=time.monotonic() - age, _closing=closing)

    def run_stop(self, app, shared=False):
        with patch.object(A, '_worker_fields', return_value=('w', 's', '_async_background_request')), \
             patch.object(A, '_shared', return_value=shared), patch.object(A, '_cancel_request') as cancel:
            A.stop_background_request(app)
        return cancel.called

    def test_a_row_well_under_way_is_kept(self):
        self.assertFalse(self.run_stop(self.app(5)))

    def test_a_row_past_the_limit_is_stopped(self):
        self.assertTrue(self.run_stop(self.app(A.KEEP_BACKGROUND_ROW_MAX_S + 1)))

    def test_the_helper_waits_for_a_row_under_way(self):
        with patch.object(A, '_worker_fields', return_value=('w', 's', '_async_background_request')), patch.object(A, '_shared', return_value=False):
            self.assertTrue(A._background_row_running(self.app(5)))
            self.assertFalse(A._background_row_running(self.app(.1)))
            self.assertFalse(A.helper_allowed(self.app(5)))

    def test_a_row_just_begun_is_stopped(self):
        self.assertTrue(self.run_stop(self.app(.1)))

    def test_a_shared_child_is_stopped(self):
        self.assertTrue(self.run_stop(self.app(5), shared=True))

    def test_closing_stops(self):
        self.assertTrue(self.run_stop(self.app(5, closing=True)))

    def test_nothing_asked(self):
        app = NS(_async_background_request=None)
        self.assertTrue(self.run_stop(app))

    def test_a_context_request_is_stopped(self):
        self.assertTrue(self.run_stop(self.app(5, scope='helper')))


class Pause(unittest.TestCase):
    def test_sets_and_clears_the_flag(self):
        flag = NS(value=0)
        app = NS(_prefetch_worker=NS(pause_flag=flag))
        A.pause_background(app, True)
        self.assertEqual(flag.value, 1)
        A.pause_background(app, False)
        self.assertEqual(flag.value, 0)

    def test_no_child_is_no_trouble(self):
        A.pause_background(NS(), True)
        A.pause_background(NS(_prefetch_worker=NS()), True)


if __name__ == '__main__':
    unittest.main()
