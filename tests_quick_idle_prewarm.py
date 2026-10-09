# -*- coding: utf-8 -*-
"""Quick idle preparation cannot supersede text work or another window."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import quick_analysis as Q
from tests_input_pause import Root
from tests_quick_async import Widget

class QuickIdlePrewarmTests(unittest.TestCase):
    def make(self):
        worker=Mock();worker.process.is_alive.return_value=True
        app=SimpleNamespace(root=Root(),_quick_text=Widget(),_quick_worker=worker,settings={},
                            _quick_after_id=None,_quick_job=None)
        app._quick_worker_state=Q.state_key(app)
        return app,worker

    def run_idle(self,app):app.root.run(app._quick_prewarm_after_id)

    def test_idle_sends_only_public_resources_once_per_worker(self):
        a,w=self.make()
        with patch.object(Q,'snapshot',side_effect=AssertionError('No snapshot')),\
             patch.object(a._quick_text,'get',side_effect=AssertionError('No text read')):
            Q.queue_idle_prewarm(a);Q.queue_idle_prewarm(a)
            self.assertEqual(len(a.root.jobs),1)
            self.assertEqual(a.root.jobs[a._quick_prewarm_after_id][0],1200)
            self.run_idle(a);Q.queue_idle_prewarm(a)
        self.assertEqual(a.root.jobs,{})
        w.submit.assert_called_once_with({'kind':'warmup'})

    def test_edit_timer_and_live_job_always_take_priority(self):
        for field,value in (('_quick_after_id',900),('_quick_job',{'identifier':4}),
                            ('_quick_f2_pending',('scope','1.0')),('_closing',True)):
            with self.subTest(field=field),patch.object(Q,'_composing',return_value=False):
                a,w=self.make();Q.queue_idle_prewarm(a);setattr(a,field,value);self.run_idle(a)
                w.submit.assert_not_called()
                setattr(a,field,None);Q.queue_idle_prewarm(a);self.run_idle(a)
                w.submit.assert_called_once_with({'kind':'warmup'})

    def test_during_composition_only_idle_public_work_can_start(self):
        a,w=self.make();a._quick_after_id=9
        with patch.object(Q,'_composing',return_value=True):
            Q.queue_idle_prewarm(a);self.run_idle(a)
        w.submit.assert_called_once_with({'kind':'warmup'})
        a,w=self.make();a._quick_after_id=9;a._quick_job={'identifier':2}
        with patch.object(Q,'_composing',return_value=True):
            Q.queue_idle_prewarm(a);self.run_idle(a)
        w.submit.assert_not_called()

    def test_quiet_deadline_model_and_owner_changes_prevent_old_request(self):
        for change in ('quiet','model','widget','worker','closed','dead'):
            with self.subTest(change=change):
                a,w=self.make();Q.queue_idle_prewarm(a)
                if change=='quiet':a._quick_display_after=11
                elif change=='model':a._analysis_state_revision=1
                elif change=='widget':a._quick_text=Widget()
                elif change=='worker':a._quick_worker=Mock()
                elif change=='closed':a._quick_text=None
                else:w.process.is_alive.return_value=False
                with patch.object(Q.time,'monotonic',return_value=10):self.run_idle(a)
                w.submit.assert_not_called()

    def test_close_cancels_callback_and_retained_worker_can_keep_only_public_warmth(self):
        a,w=self.make();Q.queue_idle_prewarm(a);old=a._quick_prewarm_after_id
        callback=a.root.jobs[old][1]
        Q.close(a,keep_idle_worker=True);callback()
        w.submit.assert_not_called();self.assertNotIn(old,a.root.jobs)
        self.assertIsNone(a._quick_prewarm_after_id)
        Q.close(a);w.close.assert_called_once()

    def test_failed_submission_is_reported_without_marking_ready(self):
        a,w=self.make();w.submit.side_effect=OSError('closed');Q.queue_idle_prewarm(a)
        with patch.object(Q.traceback,'print_exc') as reported:
            self.run_idle(a);reported.assert_called_once()
        self.assertIsNot(getattr(w,'_quick_idle_prewarm_submitted',False),True)

if __name__=='__main__':unittest.main()
