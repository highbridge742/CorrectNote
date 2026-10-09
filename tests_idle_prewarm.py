import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import analysis_async as A

class IdlePrewarmTests(unittest.TestCase):
 def make(self):
  callbacks={};root=Mock();root.after.side_effect=lambda delay,fn:callbacks.setdefault('fn',fn) and 'idle-job'
  worker=SimpleNamespace(process=Mock(),submit=Mock(),close=Mock());worker.process.is_alive.return_value=True
  app=SimpleNamespace(root=root,_correction_worker=worker,_worker_state=('ready',),_async_request=None,_foreground_analysis_pending=Mock(return_value=False))
  return app,worker,callbacks
 def test_one_public_request_per_worker_without_snapshot(self):
  a,w,c=self.make()
  with patch.object(A,'snapshot',side_effect=AssertionError('No model snapshot')):
   A.queue_idle_prewarm(a);A.queue_idle_prewarm(a);a.root.after.assert_called_once();c['fn']()
  w.submit.assert_called_once_with({'kind':'warmup'});self.assertTrue(w._idle_prewarm_submitted);self.assertIsNone(a._idle_prewarm_job)
  A.queue_idle_prewarm(a);a.root.after.assert_called_once()
 def test_new_input_and_inflight_requests_have_priority(self):
  for field,value in (('_closing',True),('_async_request',('line',2)),('_worker_state',None)):
   a,w,c=self.make();A.queue_idle_prewarm(a);setattr(a,field,value);c['fn']();w.submit.assert_not_called()
  a,w,c=self.make();A.queue_idle_prewarm(a);a._foreground_analysis_pending.return_value=True;c['fn']();w.submit.assert_not_called()
  a._foreground_analysis_pending.return_value=False;A.queue_idle_prewarm(a);c['fn']();w.submit.assert_called_once()
 def test_dead_or_replaced_worker_is_not_used(self):
  a,w,c=self.make();A.queue_idle_prewarm(a);w.process.is_alive.return_value=False;c['fn']();w.submit.assert_not_called()
  a,w,c=self.make();A.queue_idle_prewarm(a);a._correction_worker=None;c['fn']();w.submit.assert_not_called()
 def test_close_cancels_timer_before_disposing_worker(self):
  a,w,c=self.make();A.queue_idle_prewarm(a);A.close(a);a.root.after_cancel.assert_called_once_with('idle-job');w.close.assert_called_once();self.assertIsNone(a._idle_prewarm_job)
 def test_submission_failure_does_not_mark_a_worker_complete(self):
  a,w,c=self.make();w.submit.side_effect=OSError('closed');A.queue_idle_prewarm(a)
  with patch.object(A.traceback,'print_exc') as report:c['fn']();report.assert_called_once()
  self.assertFalse(getattr(w,'_idle_prewarm_submitted',False))

if __name__=='__main__':unittest.main()
