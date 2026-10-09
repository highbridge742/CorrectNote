"""Only a public-table-only live worker can survive first-run setup."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import analysis_async,initial_setup
from tests_initial_setup import Scheduler
from vocabulary import VocabularyStore

class InitialWorkerReuseTests(unittest.TestCase):
 def make_app(self):
  fg=Mock();bg=Mock();fg.process.is_alive.return_value=True
  a=SimpleNamespace(_correction_worker=fg,_worker_state=None,_async_request=None,
      _prefetch_worker=bg,_prefetch_worker_state=('old',),_async_background_request=('old',1))
  return a,fg,bg
 def test_keeps_only_prewarmed_foreground_and_shutdown_still_closes_it(self):
  import quick_analysis
  a,fg,bg=self.make_app()
  with patch.object(quick_analysis,'close') as quick:
   analysis_async.close(a,keep_prewarmed=True)
   self.assertIs(a._correction_worker,fg);fg.close.assert_not_called()
   bg.close.assert_called_once();quick.assert_called_once_with(a)
   self.assertIsNone(a._prefetch_worker);self.assertIsNone(a._async_background_request)
   analysis_async.close(a)
   fg.close.assert_called_once();self.assertIsNone(a._correction_worker)
 def test_snapshot_pending_request_and_exited_process_cannot_be_reused(self):
  import quick_analysis
  for state,request,alive in [(('model',1),None,True),(None,('line',5),True),(None,None,False)]:
   with self.subTest(state=state,request=request,alive=alive):
    a,fg,bg=self.make_app();a._worker_state=state;a._async_request=request;fg.process.is_alive.return_value=alive
    with patch.object(quick_analysis,'close'):analysis_async.close(a,keep_prewarmed=True)
    fg.close.assert_called_once();self.assertIsNone(a._correction_worker)
 def test_import_start_preserves_pending_identity_until_disposal(self):
  import quick_analysis
  a,fg,bg=self.make_app();a._async_request=('line',2)
  a.root=Scheduler();a.status=Mock();a.store=VocabularyStore();a._cancel_analysis_job=Mock()
  collector=Mock()
  with patch.object(quick_analysis,'close'),patch.object(initial_setup,'Worker',return_value=collector):
   initial_setup.start(a)
   fg.close.assert_called_once();self.assertIsNone(a._correction_worker)
   self.assertIs(a._initial_setup['worker'],collector)
   initial_setup.close(a);collector.close.assert_called_once()
 def test_completed_import_passes_new_snapshot_to_the_retained_worker(self):
  import quick_analysis
  a,fg,bg=self.make_app();a.root=Scheduler();a.status=Mock();a.store=VocabularyStore();a.store.save=Mock()
  a.dict_index=SimpleNamespace(ready=True);a._cancel_analysis_job=Mock();a._mark_setup_done=Mock();a._update_status=Mock()
  a._invalidate_analysis_cache=Mock();a._warm_then_analyze=Mock();collector=Mock()
  collector.poll.return_value=[('しりょう','資料','名詞',1)]
  with patch.object(quick_analysis,'close'),patch.object(initial_setup,'Worker',return_value=collector):
   initial_setup.start(a);self.assertIs(a._correction_worker,fg)
   while a._initial_setup is not None:a.root.next()
   collector.close.assert_called_once();fg.close.assert_not_called()
   a._invalidate_analysis_cache.assert_called_once_with(keep_current=False)
   task=dict(kind='prepare',lines=['現在の資料です。']);snapshot={'updated':True};scope=('new',)
   with patch.object(analysis_async,'state_key',return_value=('new-model',)),patch.object(analysis_async,'snapshot',return_value=snapshot) as snapshot_fn:
    analysis_async._request(a,task,scope)
    snapshot_fn.assert_called_once_with(a);fg.submit.assert_called_once_with(task,snapshot)
   self.assertEqual(a._worker_state,('new-model',));analysis_async.close(a)

if __name__=='__main__':unittest.main()
