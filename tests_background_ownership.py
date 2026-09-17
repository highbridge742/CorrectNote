# -*- coding: utf-8 -*-
"""Background ownership and eligibility, using the real application methods."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import app,analysis_work_app as work,analysis_async,tab_analysis
from analysis_work import Document
from session import SessionStore,new_tab

class BackgroundOwnershipTests(unittest.TestCase):
 def setUp(self):
  a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
  a.session=SessionStore();a.session.tabs=[new_tab(text='現在のメモ'),new_tab(text='資料です。\n末尾'),new_tab(text='資料です。\n末尾')]
  a.settings={'input_method':'kana'};a.store=SimpleNamespace(revision=lambda:0)
  a.root=Mock();a._bg_texts=[];a._analyze_todo=[];a._analyze_pos=0;a._bg=None;a._bg_job=None
  a._analysis_cache={};a._analysis_cache_dependencies={};a._analysis_stale=set()
  work.select_document(a,'現在のメモ')
  for i,reading in ((1,'しりょう'),(2,'しりお')):
   owner=work.owner_for_tab(a,a.session.tabs[i]);doc=Document(owner,a.session.tabs[i]['text'])
   doc.remember(0,2,'資料',reading);a._input_documents[owner]=doc
 def state(self,index):
  a=self.a;owner=work.owner_for_tab(a,a.session.tabs[index]);text=a.session.tabs[index]['text']
  return dict(owner=owner,text=text,lines=text.split('\n'),ctx={},pos=1,
   results=[dict(original='資料です。',corrected='資料です。'),None],
   dependencies=analysis_async.state_key(a),readings=tab_analysis._readings(a,owner),
   work_epoch=a._work_epoch,words={},attested={},units={},suspect_units={})
 def test_text_only_cache_cannot_skip_a_document_with_live_ime(self):
  a=self.a;text=a.session.tabs[1]['text']
  a._analysis_cache[text]=[dict(original=line,corrected=line) for line in text.split('\n')]
  a._analysis_cache_dependencies[text]=analysis_async.state_key(a)
  a._start_background_tabs()
  self.assertEqual([owner for owner,text in a._bg_texts],
   [work.owner_for_tab(a,a.session.tabs[i]) for i in (1,2)])
 def test_identical_text_does_not_take_another_owners_partial_work(self):
  a=self.a;first=self.state(1);second=self.state(2)
  a._bg=first;a._stop_background_tabs()
  a._bg_texts=[(second['owner'],second['text'])]
  self.assertTrue(a._bg_step_once())
  self.assertEqual(a._bg['owner'],second['owner'])
  self.assertEqual(a._bg['readings'],second['readings'])
 def test_two_identical_documents_keep_their_own_partial_values(self):
  a=self.a;first=self.state(1);second=self.state(2)
  a._bg=first;a._stop_background_tabs();a._bg=second;a._stop_background_tabs()
  self.assertEqual(len(a._bg_parked),2)
  a._bg_texts=[(first['owner'],first['text'])];a._bg_step_once()
  self.assertEqual(a._bg['owner'],first['owner'])
  self.assertEqual(a._bg['pos'],1)


 def test_pending_input_parks_background_and_resumes_without_an_explicit_start(self):
  a=self.a;state=self.state(1);a._bg=state;a._after_id='input-check'
  a._bg_step()
  self.assertIsNone(a._bg)
  self.assertEqual(a._bg_parked[state['owner']]['pos'],1)
  delay,callback=a.root.after.call_args.args
  self.assertEqual(delay,300)
  a._after_id=None;callback()
  self.assertIsNone(a._bg_start_job)
  self.assertEqual(a._bg_texts[0][0],state['owner'])
  a._bg_step_once()
  self.assertEqual(a._bg['pos'],1)
 def test_epoch_change_preserves_completed_background_rows(self):
  a=self.a;state=self.state(1);a._bg=state;a._work_epoch+=1
  a._bg_step_once()
  self.assertIsNone(a._bg)
  self.assertEqual(a._bg_parked[state['owner']]['pos'],1)
 def test_new_foreground_progress_merges_with_prior_background_rows(self):
  a=self.a;first=self.state(1)
  tab_analysis.park_background(a,first)
  later=self.state(1);later['results']=[None,dict(original='末尾',corrected='末尾')]
  tab_analysis.park_background(a,later)
  saved=a._bg_parked[first['owner']]
  self.assertEqual(saved['pos'],2)
  self.assertTrue(all(saved['results']))
 def test_scheduled_background_start_is_cancelled_on_close_or_new_analysis(self):
  a=self.a;a._queue_background_tabs();job=a._bg_start_job
  a._stop_background_tabs()
  a.root.after_cancel.assert_any_call(job)
  self.assertIsNone(a._bg_start_job)


 def test_incomplete_partial_row_is_not_counted_as_completed(self):
  a=self.a;state=self.state(1)
  state['results'][0]['analysis_status']='incomplete'
  tab_analysis.park_background(a,state)
  parked=a._bg_parked[state['owner']]
  self.assertEqual(parked['pos'],0)
  self.assertIsNone(parked['results'][0])
 def test_incomplete_text_cache_does_not_suppress_background_work(self):
  a=self.a;text=a.session.tabs[1]['text']
  a._input_documents.clear()
  a._analysis_cache[text]=[dict(original=line,corrected=line,analysis_status='incomplete') for line in text.split('\n')]
  a._analysis_cache_dependencies[text]=analysis_async.state_key(a)
  self.assertIsNone(tab_analysis.text_results(a,text,work.owner_for_tab(a,a.session.tabs[1])))
  a._start_background_tabs()
  self.assertEqual(len(a._bg_texts),2)

if __name__=='__main__':unittest.main()
