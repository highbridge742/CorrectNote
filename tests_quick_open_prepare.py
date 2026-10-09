# -*- coding: utf-8 -*-
"""Optional preparation never supersedes input or survives its quick window."""
import unittest
from unittest.mock import patch
import tests_quick_composition_prepare as base
import tests_quick_async as asynchronous
import quick_analysis as Q

class QuickOpenPrepareTests(base.QuickCompositionPrepareTests):
    def scheduled(self):
        Q.schedule_prepare(self.app)
        return self.app.root.after.call_args[0][1]
    def test_opening_only_schedules_then_prepares_without_text_analysis(self):
        ready=self.scheduled();self.worker.submit.assert_not_called()
        self.assertEqual(self.app.root.after.call_args[0][0],40)
        with patch.object(self.widget,'get',side_effect=AssertionError('preparation must not read text')):
            ready()
        self.assertEqual(self.worker.submit.call_args[0][0],{'kind':'quick_prepare'})
        self.app._finish_quick_analysis.assert_not_called()
        self.assertIsNone(getattr(self.app,'_quick_job',None))
        Q.schedule_prepare(self.app);self.assertEqual(self.app.root.after.call_count,1)
    def test_replaced_widget_makes_the_pending_callback_inert(self):
        ready=self.scheduled();self.app._quick_text=asynchronous.Widget('別の窓');ready()
        self.worker.submit.assert_not_called();self.snapshot.assert_not_called()
    def test_close_cancels_preparation_even_before_any_worker_exists(self):
        ready=self.scheduled();Q.close(self.app);ready()
        self.app.root.after_cancel.assert_called_once()
        self.worker.submit.assert_not_called();self.snapshot.assert_not_called()
        self.assertIsNone(self.app._quick_prepare_after_id)
    def test_first_committed_input_cannot_be_superseded_by_preparation(self):
        ready=self.scheduled();Q.start(self.app);ready()
        self.assertEqual(self.worker.submit.call_count,1)
        self.assertEqual(self.worker.submit.call_args[0][0]['kind'],'quick')
        self.worker.poll.assert_called_once_with(1)
    def test_completed_input_also_makes_late_preparation_unnecessary(self):
        ready=self.scheduled();Q.start(self.app)
        self.worker.poll.return_value=self.completed();Q.start(self.app);ready()
        self.assertEqual(self.worker.submit.call_count,1)
        self.app._finish_quick_analysis.assert_called_once()
    def test_opening_preparation_failure_is_optional_and_not_repeated(self):
        ready=self.scheduled();self.worker.submit.side_effect=[RuntimeError('prepare failure'),1]
        with patch.object(Q.traceback,'print_exc') as report:
            ready();Q.prepare(self.app);report.assert_called_once()
        self.assertEqual(self.worker.submit.call_count,1)
        Q.start(self.app);self.assertEqual(self.worker.submit.call_count,2)
        self.app.status.config.assert_not_called()
