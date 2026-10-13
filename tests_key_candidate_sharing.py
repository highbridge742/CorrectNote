# -*- coding: utf-8 -*-
import unittest,time,json
from pathlib import Path
from unittest.mock import patch
import romaji_repair as R,halfwidth as H,corrector as C
from analysis_context import request_scope,SupersededAnalysis
from tests_analysis_async import initial
from last_choice import set_active
from correction_entry import correct_line
RAW='shiryouwohozinshimasu'

class CandidateSharingTests(unittest.TestCase):
 def setUp(self):self.token=R._READINGS.set({})
 def tearDown(self):R._READINGS.get().clear();R._READINGS.reset(self.token)
 def test_identical_complete_search_reuses_only_the_pure_enumeration(self):
  original=H.romaji_to_kana
  with patch.object(H,'romaji_to_kana',wraps=original) as calls:
   first=R.one_key_readings(RAW);count=calls.call_count
   second=R.one_key_readings(RAW)
   self.assertIs(first,second);self.assertGreater(count,10);self.assertEqual(calls.call_count,count)
  self.assertEqual(first.state,'complete')
  self.assertTrue(any(row[0]=='しりょうをほぞんします' for row in first.candidates))

 def test_limits_do_not_reuse_or_publish_partial_enumerations(self):
  complete=R.one_key_readings(RAW)
  small=R.one_key_readings(RAW,state_limit=1)
  self.assertEqual(small.state,'state_limit');self.assertEqual(small.examined,1)
  self.assertEqual(len(R._READINGS.get()),1)
  self.assertEqual(R.one_key_readings(RAW,input_limit=3).state,'input_limit')
  self.assertIs(R.one_key_readings(RAW),complete)

 def test_cached_hit_still_observes_superseded_input(self):
  R.one_key_readings(RAW)
  with request_scope(lambda:True):
   with self.assertRaises(SupersededAnalysis):R.one_key_readings(RAW)

 def test_cache_is_bounded_without_changing_recomputed_candidates(self):
  first=R.one_key_readings(RAW)
  for value in ('kan','ken','kin','kon','kun','san','sen','sin','son'):
   R.one_key_readings(value)
   self.assertLessEqual(len(R._READINGS.get()),8)
  self.assertNotIn((RAW,4096,96),R._READINGS.get())
  self.assertEqual(R.one_key_readings(RAW),first)

 def test_final_cancellation_does_not_publish_a_completed_but_obsolete_search(self):
  count=[0]
  def checked(*args,**kwargs):
   count[0]+=1
   if count[0]>=2:raise SupersededAnalysis()
  with patch('analysis_context.check_current_request',side_effect=checked):
   with self.assertRaises(SupersededAnalysis):R.one_key_readings('kan')
  self.assertFalse(R._READINGS.get())

class CandidateSharingEntryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.state=initial()
 @classmethod
 def tearDownClass(cls):set_active(None)
 def call(self,source):
  a=self.state
  return correct_line(source,a.store,input_method='romaji',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
 def test_repeated_fields_keep_source_positions_and_release_all_cached_text(self):
  pools=[];original=R.one_key_readings;hits=[]
  def observe(typed,*args,**kw):
   pools.append(R._READINGS.get());value=original(typed,*args,**kw);hits.append(value);return value
  with patch.object(R,'one_key_readings',side_effect=observe):r=self.call(RAW+'\t'+RAW)
  self.assertEqual(r['corrected'],'資料を保存します\t資料を保存します')
  self.assertEqual(r['diagnosis']['replaced_odd_spans'],[[0,len(RAW)],[len(RAW)+1,2*len(RAW)+1]])
  self.assertEqual(r['odd_spans'],[]);self.assertEqual(r['analysis_status'],'complete')
  self.assertEqual(len(hits),2);self.assertIs(hits[0],hits[1])
  self.assertTrue(all(pool=={} for pool in pools));self.assertIsNone(R._READINGS.get())

 def test_exception_also_clears_owned_dictionary_before_restoring_scope(self):
  pools=[];original=R.one_key_readings
  def fail(typed,*args,**kw):
   value=original(typed,*args,**kw);pools.append(R._READINGS.get())
   self.assertTrue(pools[-1]);raise SupersededAnalysis()
  with patch.object(R,'one_key_readings',side_effect=fail):
   with self.assertRaises(SupersededAnalysis):self.call(RAW)
  self.assertTrue(all(pool=={} for pool in pools));self.assertIsNone(R._READINGS.get())


import contextvars
import halfwidth as H
from analysis_context import request_scope,SupersededAnalysis
RAW="shiryouwohozinshimasu"

class CandidateSharingPublicationTests(unittest.TestCase):
    def test_publication_checks_cancellation_even_inside_poll_cadence(self):
        pool={};token=R._READINGS.set(pool);cancelled=[False];calls=[0]
        decode=H.romaji_to_kana
        def reading(text):
            value=decode(text);calls[0]+=1
            # One mandatory entry and the first frequent checkpoint have
            # already passed; expire the request before publishing rows.
            if calls[0]==80:cancelled[0]=True
            return value
        try:
            with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(H,'romaji_to_kana',side_effect=reading):
                with self.assertRaises(SupersededAnalysis):R.one_key_readings(RAW)
            self.assertFalse(pool)
        finally:pool.clear();R._READINGS.reset(token)

class IndependentRequestOwnership(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.addCleanup(set_active,None)
    def call(self,source):
        a=self.a
        return correct_line(source,a.store,input_method='romaji',dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None)
    def test_outer_pool_and_copied_context_are_not_cross_request_history(self):
        outer={'sentinel':'outer owner'};token=R._READINGS.set(outer)
        original=R.one_key_readings;contexts=[];pools=[]
        def observe(*args,**kwargs):
            result=original(*args,**kwargs);pools.append(R._READINGS.get())
            contexts.append(contextvars.copy_context());return result
        try:
            with patch.object(R,'one_key_readings',side_effect=observe):
                first=self.call(RAW);second=self.call(RAW)
            self.assertEqual(first,second)
            self.assertGreaterEqual(len(pools),2)
            self.assertIsNot(pools[0],pools[-1])
            self.assertTrue(all(pool=={} and pool is not outer for pool in pools))
            self.assertTrue(all(ctx.run(R._READINGS.get)=={} for ctx in contexts))
            self.assertIs(R._READINGS.get(),outer)
            self.assertEqual(outer,{'sentinel':'outer owner'})
        finally:R._READINGS.reset(token)
    def test_shared_keys_cannot_bypass_second_field_final_gate(self):
        source=RAW+'\t'+RAW;start=len(RAW)+1;gate=C._check_replacement
        original=R.one_key_readings;seen=[]
        def keys(*args,**kwargs):
            value=original(*args,**kwargs);seen.append(value);return value
        def checked(line,edit,*args,**kwargs):
            if line==source and edit[0]>=start and '保存' in edit[2]:return None,'independent_partial_block'
            return gate(line,edit,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=checked),patch.object(R,'one_key_readings',side_effect=keys):
            row=self.call(source)
        self.assertEqual(row['corrected'],'資料を保存します\t'+RAW)
        self.assertEqual(row['odd_spans'],[(start,len(source))])
        self.assertEqual(row['analysis_status'],'complete')
        self.assertEqual(row['diagnosis']['replaced_odd_spans'],[[0,len(RAW)]])
        self.assertEqual(row['diagnosis']['unreplaced_odd_spans'],[[start,len(source)]])
        self.assertGreaterEqual(len(seen),2);self.assertIs(seen[0],seen[1])
        self.assertIsNone(R._READINGS.get())

if __name__=='__main__':unittest.main()
