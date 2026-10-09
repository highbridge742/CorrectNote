"""F2 owns the positioned committed readings without weakening edit identity."""
import unittest
from types import SimpleNamespace
import quick_analysis as Q
import analysis_work_app as W
from ime_commit_ranges import CommitRanges
import tests_quick_input_pause as pause
import tests_quick_async as asynchronous


class QuickF2CommitTests(unittest.TestCase):
    setUp=pause.QuickInputPauseTests.setUp
    completed=pause.QuickInputPauseTests.completed
    edit=pause.QuickInputPauseTests.edit
    tick=pause.QuickInputPauseTests.tick

    def queued_commit(self,reserve_before_edit=False):
        a=self.app;self.widget.text='';W.quick_document(a,'')
        if reserve_before_edit:Q.schedule_change(a)
        ranges=CommitRanges();ranges.set_owner(self.widget);ranges.begin()
        a._quick_ime_result_events=SimpleNamespace(ranges=ranges,take=lambda:())
        ranges.result('資料','しりょう');self.widget.text='資料'
        W.quick_edited(a,'資料',False,(0,0));ranges.finish()
        if not reserve_before_edit:Q.schedule_change(a)

    def request_f2(self):
        a=self.app
        if getattr(a,'_quick_after_id',None):
            a.root.after_cancel(a._quick_after_id);a._quick_after_id=None
        Q.defer_f2(a);Q.start(a)

    def test_first_f2_after_positioned_commit_opens_with_current_reading(self):
        a=self.app;self.queued_commit();deadline=a._quick_display_after
        self.now+=.04;self.request_f2()
        self.assertIsNotNone(a._quick_f2_pending)
        task=self.worker.submit.call_args[0][0]
        self.assertEqual([(x.start,x.end,x.surface,x.reading) for x in task['readings'][0]],
                         [(0,2,'資料','しりょう')])
        self.worker.poll.return_value=self.completed();self.tick(.04)
        a._finish_quick_analysis.assert_called_once();a._on_quick_f2.assert_called_once()
        self.assertLess(self.now,deadline);self.assertEqual(a._quick_display_after,deadline)
        self.assertIsNone(a._quick_f2_pending)

    def test_reading_drain_does_not_absorb_real_edit_before_key_release(self):
        a=self.app;self.queued_commit(reserve_before_edit=True)
        reserved=a._quick_pause_identity;deadline=a._quick_display_after
        self.now+=.08;self.request_f2()
        self.assertEqual(a._quick_pause_identity,reserved)
        self.assertEqual(a._quick_display_after,deadline)
        self.now+=.01;Q.schedule_change(a)
        self.assertNotEqual(a._quick_pause_identity,reserved)
        self.assertAlmostEqual(a._quick_display_after,10.34)

    def test_cursor_move_still_invalidates_f2_after_committed_reading(self):
        a=self.app;self.queued_commit();self.request_f2()
        self.widget.position='1.0';self.worker.poll.return_value=self.completed()
        self.tick(.08);a._on_quick_f2.assert_not_called()
        self.tick(.18);a._on_quick_f2.assert_not_called()
        self.assertIsNone(a._quick_f2_pending)

    def test_a_b_a_edit_still_invalidates_f2_and_reading(self):
        a=self.app;self.queued_commit();self.request_f2()
        self.edit('別');self.edit('資料')
        self.worker.poll.return_value=self.completed();self.tick(.26)
        self.assertIsNone(a._quick_f2_pending);a._on_quick_f2.assert_not_called()
        self.assertEqual(self.worker.submit.call_count,2)
        self.assertEqual(self.worker.submit.call_args[0][0]['readings'][0],())

    def test_new_widget_cannot_inherit_old_f2_or_reading(self):
        a=self.app;self.queued_commit();self.request_f2()
        a._quick_text=asynchronous.Widget('資料')
        self.worker.poll.return_value=self.completed();self.tick(.08)
        self.assertIsNone(a._quick_f2_pending);a._on_quick_f2.assert_not_called()
        self.assertEqual(self.worker.submit.call_args[0][0]['readings'][0],())

    def test_composition_still_blocks_analysis_and_new_edit_invalidates_f2(self):
        a=self.app;self.queued_commit();self.composing.return_value=True;self.request_f2()
        self.assertEqual(self.worker.submit.call_args[0][0],{'kind':'quick_prepare'})
        a._finish_quick_analysis.assert_not_called();a._on_quick_f2.assert_not_called()
        self.edit('次の確定');self.composing.return_value=False
        self.worker.poll.return_value=self.completed();self.tick(.26)
        self.assertIsNone(a._quick_f2_pending);a._on_quick_f2.assert_not_called()
        self.assertEqual(self.worker.submit.call_args[0][0]['lines'],['次の確定'])


if __name__=='__main__':unittest.main()
