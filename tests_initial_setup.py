# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import initial_setup,analysis_worker,janome_import
from vocabulary import VocabularyStore

class Scheduler:
 def __init__(self):self.jobs={};self.serial=0
 def after(self,delay,callback):
  self.serial+=1;self.jobs[self.serial]=callback;return self.serial
 def after_cancel(self,job):self.jobs.pop(job,None)
 def next(self):
  key=next(iter(self.jobs));self.jobs.pop(key)()

class InitialSetupTests(unittest.TestCase):
 def setUp(self):
  self.a=SimpleNamespace(root=Scheduler(),status=Mock(),store=VocabularyStore(),dict_index=SimpleNamespace(ready=True),
   _cancel_analysis_job=Mock(),_mark_setup_done=Mock(),_update_status=Mock(),_warm_then_analyze=Mock(),_invalidate_analysis_cache=Mock())
  self.a.store.save=Mock()
  self.worker=Mock();self.worker.poll.return_value=None
  self.patcher=patch.object(initial_setup,'Worker',return_value=self.worker);self.patcher.start()
 def tearDown(self):initial_setup.close(self.a);self.patcher.stop()
 def test_waiting_does_not_touch_store_and_application_is_batched(self):
  a=self.a;initial_setup.start(a);self.assertEqual(a.store.to_list(),[])
  a.root.next();self.assertEqual(a.store.to_list(),[])
  rows=[('よみ'+str(i),'語'+str(i),'名詞',1) for i in range(601)]
  self.worker.poll.return_value=rows;a.root.next()
  self.assertTrue(0<len(a.store.to_list())<=250)
  self.assertIsNotNone(a._initial_setup)
  while a._initial_setup is not None:a.root.next()
  self.assertEqual(len(a.store.to_list()),601)
  a._mark_setup_done.assert_called_once_with(dictionary=True,index=True)
  a._warm_then_analyze.assert_called_once()
 def test_collected_rows_wait_for_store_reader_to_finish(self):
  a=self.a;a._warmup={'done':False};initial_setup.start(a)
  self.worker.poll.return_value=[('しりょう','資料','名詞',1)];a.root.next()
  self.assertEqual(a.store.to_list(),[])
  self.worker.close.assert_called_once();a._mark_setup_done.assert_not_called()
  a._warmup=None;a.root.next()
  self.assertEqual(len(a.store.to_list()),1)
  a._mark_setup_done.assert_called_once_with(dictionary=True,index=True)
 def test_close_cancels_poll_and_worker_without_marking_setup_complete(self):
  a=self.a;initial_setup.start(a);callback=next(iter(a.root.jobs.values()))
  initial_setup.close(a)
  self.assertFalse(a.root.jobs);self.worker.close.assert_called_once()
  callback();a._mark_setup_done.assert_not_called();self.assertEqual(a.store.to_list(),[])
 def test_worker_error_finishes_with_existing_dictionary(self):
  a=self.a;initial_setup.start(a);self.worker.poll.side_effect=RuntimeError('test failure')
  a.root.next();self.assertIsNone(a._initial_setup)
  a._mark_setup_done.assert_called_once_with(dictionary=False,index=True)
  a._warm_then_analyze.assert_called_once()
 def test_storage_failure_does_not_escape_to_tk(self):
  a=self.a;a.store.save.side_effect=OSError('test failure')
  initial_setup.start(a);self.worker.poll.return_value=[('しりょう','資料','名詞',1)];a.root.next()
  self.assertIsNone(a._initial_setup)
  a._mark_setup_done.assert_called_once_with(dictionary=False,index=True)
 def test_shared_collector_preserves_import_arguments_and_only_new(self):
  rows=[('しりょう','資料','名詞',5),('ひづけ','日付','名詞',2)]
  store=Mock();store.to_list.return_value=[dict(reading='しりょう',surface='資料')]
  with patch.object(janome_import,'collect_import_entries',return_value=rows):
   self.assertEqual(analysis_worker.Runtime().execute(dict(kind='initial_dictionary')),rows)
   self.assertEqual(janome_import.import_from_janome(store,only_new=True),1)
  store.add.assert_called_once_with('ひづけ','日付','名詞',world=2)

if __name__=='__main__':unittest.main()
