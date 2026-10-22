# -*- coding: utf-8 -*-
"""Quick input starts its work for text that arrives without a key release
(2026-10-21: an IME commit left 「興亜劇」 uncorrected in quick input only)."""
import unittest
from unittest.mock import patch
import quick_analysis as Q
import tests_quick_async as base
from tests_input_pause import Root


class QuickContentChangedTests(unittest.TestCase):
    def setUp(self):
        base.QuickAsyncTests.setUp(self)
        self.app.root=Root();self.now=10.0
        clock=patch.object(Q.time,'monotonic',side_effect=lambda:self.now)
        clock.start();self.addCleanup(clock.stop)

    completed=base.QuickAsyncTests.completed
    edit=base.QuickAsyncTests.edit

    def tick(self,seconds=0):
        self.now+=seconds
        job=self.app._quick_after_id
        self.app.root.run(job);self.app._quick_after_id=None
        Q.start(self.app)

    def test_idle_change_without_key_release_starts_the_same_work(self):
        a=self.app;a._quick_after_id=None
        Q.content_changed(a)
        self.assertEqual(a.root.jobs[a._quick_after_id][0],Q.COMPUTE_DELAY_MS)
        self.assertAlmostEqual(a._quick_display_after,10+Q.DISPLAY_QUIET_MS/1000)
        self.tick(.08);self.worker.submit.assert_called_once()
        self.worker.poll.return_value=self.completed();self.tick(.2)
        a._finish_quick_analysis.assert_called_once()

    def test_pending_timer_keeps_its_pause_and_reads_the_new_text(self):
        a=self.app;Q.schedule_change(a);job=a._quick_after_id;deadline=a._quick_display_after
        self.tick(.04);job=a._quick_after_id
        self.edit('確定した文');self.now+=.03;Q.content_changed(a)
        self.assertEqual(a._quick_after_id,job);self.assertEqual(a._quick_display_after,deadline)
        self.tick(.04)
        self.assertEqual(self.worker.submit.call_count,2)
        self.assertEqual(self.worker.submit.call_args[0][0]['lines'],['確定した文'])

    def test_closed_window_does_nothing(self):
        a=self.app;a._quick_after_id=None;a._quick_text=None
        Q.content_changed(a)
        self.assertIsNone(a._quick_after_id);self.worker.submit.assert_not_called()


if __name__=='__main__':
    unittest.main()
