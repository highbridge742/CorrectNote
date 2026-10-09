# -*- coding: utf-8 -*-
"""Quick correction remains asynchronous and bound to one live edit generation."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from analysis_work import Document
import analysis_work_app as work
import quick_analysis as Q
from analysis_worker import WorkerExitedError


class Widget:
    def __init__(self,text='元の文'):self.text=text;self.position='1.3'
    def get(self,*args):return self.text
    def index(self,*args):return self.position
    def winfo_id(self):return 99


class QuickAsyncTests(unittest.TestCase):
    def setUp(self):
        self.widget=Widget();self.worker=Mock();self.worker.process.is_alive.return_value=True
        self.worker.submit.side_effect=range(1,30);self.worker.poll.return_value=None
        self.app=SimpleNamespace(_quick_text=self.widget,settings={'input_method':'kana'},root=Mock(),status=Mock(),
            _analyze_quick=Mock(),_finish_quick_analysis=Mock(return_value=False),_autofix_live_records=Mock(return_value=[]),_on_quick_f2=Mock())
        self.worker_patch=patch.object(Q,'Worker',return_value=self.worker);self.worker_patch.start()
        self.snapshot_patch=patch.object(Q,'snapshot',return_value={});self.snapshot=self.snapshot_patch.start()
        self.composition_patch=patch.object(Q,'_composing',return_value=False);self.composing=self.composition_patch.start()
        self.addCleanup(self.worker_patch.stop);self.addCleanup(self.snapshot_patch.stop);self.addCleanup(self.composition_patch.stop)
    def completed(self):return dict(results=[{'original':self.widget.text,'corrected':self.widget.text}],units=[[]],corrected_units=[(self.widget.text,[])])
    def edit(self,text):
        self.widget.text=text;work.quick_edited(self.app,text,False,None)
    def test_pending_worker_does_not_run_correction_or_block_the_caller(self):
        Q.start(self.app)
        self.worker.submit.assert_called_once();self.app._finish_quick_analysis.assert_not_called()
        self.app.root.after.assert_called_once();self.snapshot.assert_called_once()
    def test_a_b_a_edit_discards_the_earlier_identical_text_result(self):
        Q.start(self.app);first=self.app._quick_job['scope'];self.edit('別の文');self.edit('元の文')
        Q.start(self.app)
        self.assertNotEqual(first,self.app._quick_job['scope']);self.assertEqual(self.worker.submit.call_count,2)
        self.worker.poll.assert_called_with(2);self.app._finish_quick_analysis.assert_not_called()
        self.worker.poll.return_value=self.completed();Q.start(self.app)
        self.app._finish_quick_analysis.assert_called_once()
    def test_changed_model_state_resubmits_without_reusing_a_completed_result(self):
        Q.start(self.app);self.app._analysis_state_revision=1;Q.start(self.app)
        self.assertEqual(self.worker.submit.call_count,2);self.assertEqual(self.snapshot.call_count,2)
        self.worker.poll.assert_called_with(2)
    def test_completed_value_waits_for_ime_commit_without_recorrection(self):
        Q.start(self.app);self.worker.poll.return_value=self.completed();self.composing.side_effect=[False,True]
        Q.start(self.app);self.app._finish_quick_analysis.assert_not_called()
        self.composing.side_effect=None;self.composing.return_value=False;Q.start(self.app)
        self.app._finish_quick_analysis.assert_called_once();self.assertEqual(self.worker.submit.call_count,1)
        self.assertEqual(self.worker.poll.call_count,2)
    def test_explicit_calculation_is_carried_with_its_live_range(self):
        self.widget.text='8*5';doc=work.quick_document(self.app,self.widget.text)
        self.assertTrue(doc.remember_calculation(0,3,'8*5','40'))
        Q.start(self.app);task=self.worker.submit.call_args[0][0]
        self.assertEqual(task['calculations'][0],doc.calculations)
    def test_f2_opens_only_after_the_requested_units_are_ready(self):
        Q.defer_f2(self.app);Q.start(self.app);self.app._on_quick_f2.assert_not_called()
        self.worker.poll.return_value=self.completed();Q.start(self.app);self.app._on_quick_f2.assert_called_once()
        self.assertIsNone(self.app._quick_f2_pending)
    def test_cursor_move_cancels_deferred_f2(self):
        Q.defer_f2(self.app);Q.start(self.app);self.widget.position='1.0';self.worker.poll.return_value=self.completed()
        Q.start(self.app);self.app._on_quick_f2.assert_not_called()
    def test_edit_cancels_deferred_f2_even_when_text_returns(self):
        Q.defer_f2(self.app);Q.start(self.app);self.edit('別の文');self.edit('元の文')
        self.worker.poll.return_value=self.completed();Q.start(self.app);self.app._on_quick_f2.assert_not_called()
    def test_worker_exit_gets_one_retry_for_this_generation(self):
        self.worker.poll.side_effect=WorkerExitedError('exit')
        with patch.object(Q.traceback,'print_exc'):
            Q.start(self.app);self.assertEqual(self.worker.submit.call_count,1)
            Q.start(self.app);self.assertEqual(self.worker.submit.call_count,2)
            self.app.status.config.assert_called_once();self.assertIsNone(self.app._quick_job)
    def test_window_close_reuses_only_idle_live_worker(self):
        Q.start(self.app);self.worker.poll.return_value=self.completed();Q.start(self.app)
        Q.close(self.app,keep_idle_worker=True)
        self.worker.close.assert_not_called()
        self.assertIs(self.app._quick_worker,self.worker)
        self.assertIsNone(self.app._quick_worker_state)
        self.assertIsNone(self.app._quick_job)
        self.assertFalse(self.app._quick_composition_prepared)
        Q.close(self.app)
        self.worker.close.assert_called_once()
        self.assertIsNone(self.app._quick_worker)
    def test_reopened_worker_receives_fresh_snapshot_even_for_unchanged_model(self):
        with patch.object(Q,'snapshot',side_effect=({'model':1},{'model':2})) as snapshot:
            Q.start(self.app);self.worker.poll.return_value=self.completed();Q.start(self.app)
            Q.close(self.app,keep_idle_worker=True);Q.prepare(self.app)
        self.assertEqual(snapshot.call_count,2)
        self.assertEqual(self.worker.submit.call_args[0],({'kind':'quick_prepare'},{'model':2}))
        self.worker.close.assert_not_called()

    def test_idle_worker_expiry_releases_memory_when_window_stays_closed(self):
        Q.start(self.app);self.worker.poll.return_value=self.completed();Q.start(self.app)
        Q.close(self.app,keep_idle_worker=True)
        milliseconds,release=self.app.root.after.call_args[0]
        self.assertEqual(milliseconds,60000)
        self.app._quick_text=None;release()
        self.worker.close.assert_called_once();self.assertIsNone(self.app._quick_worker)
        self.assertIsNone(self.app._quick_idle_after_id)
    def test_reopening_cancels_old_expiry_without_releasing_reused_worker(self):
        Q.start(self.app);self.worker.poll.return_value=self.completed();Q.start(self.app)
        Q.close(self.app,keep_idle_worker=True)
        identifier=self.app._quick_idle_after_id;release=self.app.root.after.call_args[0][1]
        self.app.root.after_cancel.reset_mock()
        Q.schedule_prepare(self.app)
        self.app.root.after_cancel.assert_called_once_with(identifier)
        release();self.worker.close.assert_not_called()
        self.assertIs(self.app._quick_worker,self.worker)

    def test_closed_window_callbacks_do_not_cancel_idle_expiry(self):
        Q.start(self.app);self.worker.poll.return_value=self.completed();Q.start(self.app)
        Q.close(self.app,keep_idle_worker=True)
        identifier=self.app._quick_idle_after_id
        self.app._quick_text=None;self.app.root.after_cancel.reset_mock()
        Q.start(self.app);Q.schedule_prepare(self.app)
        self.assertEqual(self.app._quick_idle_after_id,identifier)
        self.app.root.after_cancel.assert_not_called()

    def test_window_close_releases_active_worker(self):
        Q.start(self.app);Q.close(self.app,keep_idle_worker=True)
        self.worker.close.assert_called_once();self.assertIsNone(self.app._quick_worker)
    def test_window_close_releases_exited_idle_worker(self):
        Q.start(self.app);self.worker.poll.return_value=self.completed();Q.start(self.app)
        self.worker.process.is_alive.return_value=False
        Q.close(self.app,keep_idle_worker=True)
        self.worker.close.assert_called_once();self.assertIsNone(self.app._quick_worker)

    def test_close_releases_worker_and_pending_callbacks(self):
        Q.defer_f2(self.app);Q.start(self.app);Q.close(self.app)
        self.worker.close.assert_called_once();self.app.root.after_cancel.assert_called_once()
        self.assertIsNone(self.app._quick_worker);self.assertIsNone(self.app._quick_f2_pending)

if __name__=='__main__':unittest.main()