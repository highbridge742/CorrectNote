import unittest,json,copy
from unittest.mock import patch
from pathlib import Path
import morphology as M,ime_spelling as I,semantic_roles as S,corrector as C,reading_segments as R
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active

class CompoundArgumentScopeTests(unittest.TestCase):
 def setUp(self):self.a=initial();self.tok=C.make_tokenizer(self.a.store);self.addCleanup(set_active,None)
 def helper(self,text,first):return I._first_compound_arguments(text,first,M.tokenize(first),M.tokenize(text))
 def line(self,text):return correct_line(text,self.a.store,input_method='romaji',dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None)
 def test_written_and_source_meaning_use_same_case_but_own_predicate(self):
  records=[];real=S.candidate_evidence
  def evidence(*args,**kwargs):records.append((args,kwargs));return real(*args,**kwargs)
  with patch.object(S,'candidate_evidence',side_effect=evidence):
   self.assertIsNotNone(self.helper('ゆうびんきょくにいきます','郵便局に行きます'))
  self.assertIn((('郵便局','いき','ます'),{'before':'ゆうびんきょくに','case':'に'}),records)
  self.assertIn((('郵便局','行き','ます'),{'before':'郵便局に','case':'に'}),records)
  self.assertIsNone(self.helper('ゆうびんきょくにいきます','郵便局に生きます'))
  self.assertIsNone(self.helper('ゆうびんきょくをのみます','郵便局を飲みます'))
 def test_written_predicate_cannot_borrow_proof_from_source_callback(self):
  real=S.candidate_evidence;seen=[]
  def evidence(noun,verb,following,**kw):
   seen.append(verb)
   return None if verb=='行き' else real(noun,verb,following,**kw)
  with patch.object(S,'candidate_evidence',side_effect=evidence):
   self.assertIsNone(self.helper('ゆうびんきょくにいきます','郵便局に行きます'))
  self.assertEqual(seen,['いき','行き'])
 def test_later_clause_or_field_cannot_close_the_original_compound_argument(self):
  for source,first in [('ゆうびんきょくに\tいきます','郵便局に\t行きます'),('ゆうびんきょくに。いきます','郵便局に。行きます'),('ゆうびんきょくにいきますがしりょうをのみます','郵便局に行きますが資料を飲みます')]:
   with self.subTest(source=source):self.assertIsNone(self.helper(source,first))
 def test_original_ascii_final_gate_rejects_entire_result_after_projection(self):
  source='yuubinkyokuniikimasu';gate=C._check_replacement;seen=[]
  def check(line,edit,*args,**kw):
   if line==source and '郵便局' in edit[2]:seen.append(edit);return None,'review_original_ascii_reject'
   return gate(line,edit,*args,**kw)
  with patch.object(C,'_check_replacement',side_effect=check):r=self.line(source)
  self.assertTrue(seen);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
 def test_partial_protected_second_field_never_uses_shortened_first_offsets(self):
  source='shoruiwohozonshimasu\tyuubinkyokuniikimasu';self.a.decisions.protect('binkyoku')
  r=self.line(source);cut=source.index('binkyoku');finish=cut+len('binkyoku')
  self.assertIn('binkyoku',r['corrected']);self.assertTrue(all(b<=cut or finish<=a for a,b in r.get('original_spans',())))
  self.assertEqual(r['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
