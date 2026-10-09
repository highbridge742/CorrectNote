"""Saved IME evidence updates keep context only under the existing model identity."""
import unittest,copy
from unittest.mock import patch,Mock
from collections import Counter
from types import SimpleNamespace
import analysis_worker as W,analysis_async as A,morphology as M
from tests_analysis_async import initial,wait

class WorkerReadingStateTests(unittest.TestCase):
 def snapshot(self,a):
  state=W.snapshot(a);state['_state_identity']=W.state_key(a);return state
 def test_reading_only_update_reuses_context_but_exposes_added_changed_and_removed_pairs(self):
  a=initial();r=W.Runtime();r.set_state(self.snapshot(a));lines=['資料を確認します。','記録を点検します。']
  before=r.prepare(lines);store=r.store;index=r.index
  for reading in ('しりょう','しりょ',''):
   if reading:a.ime_readings.remember('資料',reading)
   else:a.ime_readings.forget('資料')
   data=self.snapshot(a);r.set_state(data)
   self.assertIs(r.store,store);self.assertIs(r.index,index)
   with patch.object(M,'_tokenize_uncached',side_effect=AssertionError('unchanged rows parsed')):
    self.assertIs(r.prepare(lines),before)
   self.assertEqual(r._read_ime('資料'),a.ime_readings.readings_for('資料'))
  lines[1]='記録を再点検します。';native=M._tokenize_uncached;parsed=[]
  def parse(line):parsed.append(line);return native(line)
  with patch.object(M,'_tokenize_uncached',side_effect=parse):value=r.prepare(lines)
  self.assertEqual(parsed,[lines[1]])
  reference=W.Runtime();reference.set_state(W.snapshot(a));self.assertEqual(value,reference.prepare(lines))
 def test_all_other_model_fields_and_replaced_reading_store_force_full_reset(self):
  a=initial();data=self.snapshot(a);old=data['_state_identity'];lines=['資料です。']
  variants=[]
  for position in range(9):
   key=list(old);key[position]=('different',position);variants.append(tuple(key))
  key=list(old);key[-1]=(old[-1][0]+1,old[-1][1]);variants.append(tuple(key))
  variants.append(None)
  for key in variants:
   with self.subTest(key=key):
    r=W.Runtime();r.set_state(data);r.prepare(lines);store=r.store;new=dict(data)
    if key is None:new.pop('_state_identity')
    else:new['_state_identity']=key
    r.set_state(new);self.assertIsNot(r.store,store)
    self.assertFalse(r.prepared);self.assertFalse(r.context_lines);self.assertFalse(r.content_words)
 def test_reading_update_restores_its_own_lookup_providers(self):
  import kanji_guess,last_choice
  a=initial();r=W.Runtime();r.set_state(self.snapshot(a));owned=r.choices
  last_choice.set_active(object());kanji_guess.set_ime_readings_provider(lambda surface:['foreign'])
  a.ime_readings.remember('資料','しりょう');r.set_state(self.snapshot(a))
  self.assertIs(last_choice._ACTIVE,owned)
  self.assertEqual(kanji_guess.ime_readings_for('資料'),['しりょう'])
 def test_failed_full_reset_cannot_authorize_later_partial_update(self):
  a=initial();r=W.Runtime();data=self.snapshot(a);r.set_state(data)
  a._analysis_state_revision=1;broken=self.snapshot(a);broken.pop('entries')
  with self.assertRaises(KeyError):r.set_state(broken)
  self.assertIsNone(r._state_identity)
  a.ime_readings.remember('資料','しりょう');r.set_state(self.snapshot(a))
  self.assertEqual(r._state_identity,W.state_key(a));self.assertEqual(r._read_ime('資料'),['しりょう'])
 def test_transport_sends_complete_snapshot_and_identity_to_each_worker(self):
  workers=[]
  for background in (False,True):
   a=initial();worker=Mock();worker.process.is_alive.return_value=True;workers.append(worker)
   name,state,request=A._worker_fields(background);setattr(a,name,worker);setattr(a,state,None)
   A._request(a,{'kind':'prepare','lines':['資料']},('test',),background)
   first=worker.submit.call_args.args[1];self.assertEqual(first['_state_identity'],W.state_key(a));self.assertIn('entries',first)
   a.ime_readings.remember('資料','しりょう')
   A._request(a,{'kind':'prepare','lines':['資料']},('updated',),background)
   latest=worker.submit.call_args.args[1];self.assertEqual(latest['ime'],{'資料':['しりょう']});self.assertIn('entries',latest)
   self.assertEqual(latest['_state_identity'],W.state_key(a))
 def test_coalesced_first_state_and_reading_change_still_initialize_a_fresh_process(self):
  a=initial();worker=W.Worker();lines=['資料を確認しました。'];task={'kind':'prepare','lines':lines}
  try:
   worker.submit(task,self.snapshot(a));a.ime_readings.remember('資料','しりょう')
   actual=wait(worker,worker.submit(task,self.snapshot(a)))
   r=W.Runtime();r.set_state(W.snapshot(a));self.assertEqual(actual,r.prepare(lines))
  finally:worker.close()
 def test_real_corrections_after_reading_changes_match_a_full_state_reset(self):
  a=initial();r=W.Runtime();r.set_state(self.snapshot(a));lines=['作業が官僚しました。','資料を確認しました。'];r.prepare(lines)
  for action in ('add','replace','remove'):
   with self.subTest(action=action):
    if action=='add':a.ime_readings.remember('官僚','かんりょう')
    elif action=='replace':a.ime_readings.remember('官僚','かんりょぅ')
    else:a.ime_readings.forget('官僚')
    data=self.snapshot(a);r.set_state(data);prepared=r.prepare(lines)
    task={'kind':'line','line':lines[0],'context':prepared['context'],'attested':prepared['attested'],'input_method':'kana'}
    actual=r.execute(task)
    fresh=W.Runtime();fresh.set_state(W.snapshot(a));expected=fresh.execute(task)
    self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()
