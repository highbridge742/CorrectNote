# -*- coding: utf-8 -*-
"""Start committed quick work early, retain quiet display and latest ownership."""
import unittest
from unittest.mock import patch
import quick_analysis as Q
from tests_quick_async import QuickAsyncTests,Widget
from tests_input_pause import Root


class QuickInputPauseTests(unittest.TestCase):
    def setUp(self):
        QuickAsyncTests.setUp(self)
        self.app.root=Root();self.now=10.0
        clock=patch.object(Q.time,'monotonic',side_effect=lambda:self.now)
        clock.start();self.addCleanup(clock.stop)

    completed=QuickAsyncTests.completed
    edit=QuickAsyncTests.edit

    def tick(self,seconds=0):
        self.now+=seconds
        job=self.app._quick_after_id
        self.app.root.run(job);self.app._quick_after_id=None
        Q.start(self.app)

    def test_calculation_begins_before_unchanged_display_pause(self):
        a=self.app;Q.schedule_change(a)
        self.assertEqual(a.root.jobs[a._quick_after_id][0],80)
        self.tick(.08);self.worker.submit.assert_called_once()
        self.worker.poll.return_value=self.completed();self.tick(.04)
        self.assertTrue(129<=a.root.jobs[a._quick_after_id][0]<=131)
        a._finish_quick_analysis.assert_not_called()
        self.tick(.131)
        a._finish_quick_analysis.assert_called_once_with(self.widget.text,
            self.completed()['results'],self.completed()['units'],self.completed()['corrected_units'])
        self.assertEqual(self.worker.poll.call_count,2)

    def test_unchanged_release_keeps_compute_and_ready_display_timers(self):
        a=self.app;Q.schedule_change(a);job=a._quick_after_id;deadline=a._quick_display_after
        self.now+=.04;Q.schedule_change(a)
        self.assertEqual(a._quick_after_id,job);self.assertEqual(a._quick_display_after,deadline)
        self.tick(.04);self.worker.poll.return_value=self.completed();self.tick(.04)
        job=a._quick_after_id;self.now+=.05;Q.schedule_change(a)
        self.assertEqual(a._quick_after_id,job);self.assertEqual(a._quick_display_after,deadline)
        self.tick(.1);a._finish_quick_analysis.assert_called_once()

    def test_new_backspace_generation_owns_result_even_after_text_returns(self):
        a=self.app;Q.schedule_change(a);self.tick(.08)
        self.worker.poll.return_value=self.completed();self.tick(.04)
        before=a._quick_job['scope'];old=a._quick_after_id
        self.edit('元');self.edit('元の文');self.now+=.03;Q.schedule_change(a)
        self.assertNotIn(old,a.root.jobs);self.assertAlmostEqual(a._quick_display_after,10.4)
        self.worker.poll.return_value=None;self.tick(.08)
        self.assertNotEqual(before,a._quick_job['scope']);self.assertEqual(self.worker.submit.call_count,2)
        a._finish_quick_analysis.assert_not_called()
        self.worker.poll.return_value=self.completed();self.tick(.18)
        a._finish_quick_analysis.assert_called_once()

    def test_finished_value_stays_blocked_during_ime_without_repeat_work(self):
        a=self.app;Q.schedule_change(a);self.tick(.08)
        self.worker.poll.return_value=self.completed();self.tick(.04)
        self.composing.return_value=True;self.tick(.2)
        a._finish_quick_analysis.assert_not_called()
        self.composing.return_value=False;self.tick(.08)
        a._finish_quick_analysis.assert_called_once();self.assertEqual(self.worker.submit.call_count,1)
        self.assertEqual(self.worker.poll.call_count,2)

    def test_new_model_dependency_replaces_ready_result(self):
        a=self.app;Q.schedule_change(a);self.tick(.08)
        self.worker.poll.return_value=self.completed();self.tick(.04)
        a._analysis_state_revision=1;Q.schedule_change(a)
        self.worker.poll.return_value=None;self.tick(.08)
        self.assertEqual(self.worker.submit.call_count,2);self.assertEqual(self.snapshot.call_count,2)
        a._finish_quick_analysis.assert_not_called()

    def test_close_clears_current_deadline_and_new_widget_cannot_reuse_old_value(self):
        a=self.app;Q.schedule_change(a);self.tick(.08)
        self.worker.poll.return_value=self.completed();self.tick(.04)
        old=a._quick_after_id;Q.close(a)
        self.assertNotIn(old,a.root.jobs);self.assertIsNone(a._quick_pause_identity)
        self.assertEqual(a._quick_display_after,0);self.assertIsNone(a._quick_job)
        a._quick_text=Widget();Q.schedule_change(a)
        self.assertIs(a._quick_pause_identity[0],a._quick_text)
        self.assertEqual(a.root.jobs[a._quick_after_id][0],80)
        a._finish_quick_analysis.assert_not_called()

    def test_composition_prepares_only_resources_before_commit(self):
        a=self.app;self.composing.return_value=True;Q.schedule_change(a);self.tick(.08)
        self.worker.submit.assert_called_once_with({'kind':'quick_prepare'}, {})
        self.assertIsNone(getattr(a,'_quick_job',None));a._finish_quick_analysis.assert_not_called()
        self.edit('確定した文字');Q.schedule_change(a);self.composing.return_value=False
        self.tick(.08)
        self.assertEqual(self.worker.submit.call_args[0][0]['kind'],'quick')
        self.assertEqual(self.worker.submit.call_args[0][0]['lines'],['確定した文字'])

    def test_positioned_commit_readings_cannot_remove_current_display_pause(self):
        from types import SimpleNamespace
        from ime_commit_ranges import CommitRanges
        import analysis_work_app as work
        a=self.app;self.widget.text='';work.quick_document(a,'')
        ranges=CommitRanges();ranges.set_owner(self.widget);ranges.begin()
        a._quick_ime_result_events=SimpleNamespace(ranges=ranges,take=lambda:())
        ranges.result('資料','しりょう')
        self.widget.text='資料';work.quick_edited(a,'資料',False,(0,0));ranges.finish()
        Q.schedule_change(a);generation=a._quick_pause_identity[1];deadline=a._quick_display_after
        self.tick(.08)
        self.assertGreater(a._quick_job['scope'].generation,generation)
        self.assertEqual(self.worker.submit.call_args[0][0]['readings'][0][0].reading,'しりょう')
        self.worker.poll.return_value=self.completed();self.tick(.04)
        a._finish_quick_analysis.assert_not_called();self.assertEqual(a._quick_display_after,deadline)
        job=a._quick_after_id;Q.schedule_change(a)
        self.assertEqual(a._quick_after_id,job)
        self.tick(.131);a._finish_quick_analysis.assert_called_once()

    def test_internal_autofix_does_not_turn_arrow_release_into_another_pause(self):
        a=self.app;Q.schedule_change(a);self.tick(.08)
        self.worker.poll.return_value=self.completed()
        def autofix(*args):
            self.edit('補正後の文')
            a._quick_after_id=a.root.after(50,a._analyze_quick)
            return True
        a._finish_quick_analysis.side_effect=autofix
        self.tick(.171);job=a._quick_after_id;deadline=a._quick_display_after
        self.assertEqual(a.root.jobs[job][0],50)
        self.now+=.019;Q.schedule_change(a)
        self.assertEqual(a._quick_after_id,job);self.assertEqual(a._quick_display_after,deadline)

    def test_explicit_f2_keeps_immediate_current_units_request(self):
        a=self.app;Q.schedule_change(a);self.now+=.04
        a.root.after_cancel(a._quick_after_id);a._quick_after_id=None
        Q.defer_f2(a);Q.start(a)
        self.worker.poll.return_value=self.completed();self.tick(.04)
        a._finish_quick_analysis.assert_called_once();a._on_quick_f2.assert_called_once()
        self.assertIsNone(a._quick_after_id)

    def test_old_callback_cannot_absorb_real_edit_before_its_key_release(self):
        a=self.app;Q.schedule_change(a);reserved=a._quick_pause_identity
        self.edit('新しい入力');self.tick(.08)
        self.assertEqual(a._quick_pause_identity,reserved)
        self.now+=.01;old=a._quick_after_id;Q.schedule_change(a)
        self.assertNotIn(old,a.root.jobs)
        self.assertAlmostEqual(a._quick_display_after,10.34)
        self.assertNotEqual(a._quick_pause_identity,reserved)

    def test_leaving_mode_restarts_finished_display_without_new_typing_pause(self):
        a=self.app;Q.schedule_change(a);self.tick(.08)
        self.worker.poll.return_value=self.completed();self.tick(.18)
        self.assertIsNone(a._quick_after_id)
        old=a._quick_display_after;reserved=a._quick_pause_identity
        Q.schedule_change(a)
        self.assertIsNone(a._quick_after_id)
        Q.refresh_after_mode(a)
        self.assertEqual(a.root.jobs[a._quick_after_id][0],0)
        self.assertEqual(a._quick_display_after,old)
        self.assertEqual(a._quick_pause_identity,reserved)
        self.tick()
        self.assertEqual(self.worker.submit.call_count,2)
        self.assertEqual(a._finish_quick_analysis.call_count,2)

    def test_leaving_mode_keeps_inflight_input_deadline_and_ignores_closed_widget(self):
        a=self.app;Q.schedule_change(a);job=a._quick_after_id;deadline=a._quick_display_after
        Q.refresh_after_mode(a)
        self.assertEqual(a._quick_after_id,job)
        self.assertEqual(a._quick_display_after,deadline)
        Q.close(a);a._quick_text=None
        Q.refresh_after_mode(a)
        self.assertIsNone(a._quick_after_id)


if __name__=='__main__':unittest.main()
