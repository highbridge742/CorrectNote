# -*- coding: utf-8 -*-
"""Application cache save/load contracts, with temporary files and empty stores."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace
import app,analysis_async,analysis_work_app as work
from session import SessionStore,new_tab
from vocabulary import VocabularyStore
from decisions import DecisionStore
from last_choice import LastChoiceStore

class ApplicationCacheTests(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory(prefix='correctnote-cache-test-')
  self.path=str(Path(self.folder.name)/'analysis_cache.json')
  self.source='資料を確認します。\n明日は晴れです。'
  self.patch=patch.object(app,'ANALYSIS_CACHE_FILE',self.path);self.patch.start()
 def tearDown(self):
  self.patch.stop();self.folder.cleanup()
 def make_app(self):
  a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
  a.session=SessionStore();a.session.tabs=[new_tab(text=self.source)]
  a.settings={'input_method':'kana'};a.store=VocabularyStore();a.choices=LastChoiceStore()
  a.decisions=DecisionStore();a.context_vec=None;a.dict_index=None;a.recent_words=SimpleNamespace(words=lambda:())
  a._analysis_cache={};a._analysis_cache_dependencies={};a._analysis_stale=set()
  work.select_document(a,self.source)
  a._analyze_work=work.token(a);a._analyze_dependencies=analysis_async.state_key(a)
  a._analyze_text=self.source;a._prev_lines=self.source.split('\n');a._analyze_todo=[];a._analyze_pos=0
  a.line_results=[]
  for line in a._prev_lines:
   r=a._blank_result(line);r.pop('pending',None);a.line_results.append(r)
  a._refresh_after_analysis=Mock();a._schedule_analysis_chunk=Mock();a._finish_analysis=Mock()
  a._visible_first=lambda todo:(list(todo),len(todo));a._trace_analysis=Mock()
  return a
 def test_completed_source_cache_loads_under_new_process_identity(self):
  a=self.make_app();a._save_analysis_cache();self.assertTrue(Path(self.path).is_file())
  b=self.make_app();self.assertNotEqual(analysis_async.state_key(a),analysis_async.state_key(b))
  b._load_analysis_cache();padded=self.source+'\n\n'
  self.assertTrue(b._use_analysis_cache(padded,padded.split('\n')))
  self.assertEqual([r['original'] for r in b.line_results],padded.split('\n'))
  self.assertEqual(b._analyze_todo,[0,1])
  self.assertTrue(b._analyze_units_only)
 def test_current_live_ime_values_are_not_written_as_text_only_cache(self):
  a=self.make_app();a._input_document.remember(0,2,'資料','しりょう');a._save_analysis_cache()
  self.assertFalse(Path(self.path).exists())
 def test_pending_and_failed_rows_do_not_survive_restart(self):
  for flag in ('pending','analysis_error'):
   with self.subTest(flag=flag):
    a=self.make_app();a.line_results[0][flag]=True;a._save_analysis_cache()
    self.assertFalse(Path(self.path).exists())
 def test_old_work_generation_does_not_survive_restart(self):
  a=self.make_app();a._work_epoch+=1;a._save_analysis_cache()
  self.assertFalse(Path(self.path).exists())
 def test_old_state_is_not_saved_under_new_fingerprint(self):
  a=self.make_app();a._analysis_cache[self.source]=list(a.line_results)
  a._analysis_cache_dependencies[self.source]=a._analyze_dependencies
  a._analysis_state_revision=1;a._save_analysis_cache()
  self.assertFalse(Path(self.path).exists())
 def test_recent_word_evidence_prevents_restart_cache_reuse(self):
  a=self.make_app();a._save_analysis_cache();self.assertTrue(Path(self.path).exists())
  a.recent_words=SimpleNamespace(words=lambda:('資料',));a._save_analysis_cache()
  self.assertFalse(Path(self.path).exists())


 def test_incomplete_row_is_not_written_even_when_all_jobs_returned(self):
  a=self.make_app();a.line_results[0]['analysis_status']='incomplete';a._save_analysis_cache()
  self.assertFalse(Path(self.path).exists())

if __name__=='__main__':unittest.main()
