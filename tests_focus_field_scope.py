import unittest
from unittest.mock import patch
import morphology as M,kana_spelling as K,reading_segments as R

class FocusFieldScopeTests(unittest.TestCase):
 def test_only_actual_field_can_supply_the_nominal_case_evidence(self):
  from ime_spelling import _reinterprets_function_attachment as conflict
  source='👩🏽‍💻 はしだけ⇒はしだけを渡ります'
  first=source.index('はし');last=source.rindex('はし');seen=[]
  def evidence(before,face,after,*args,**kwargs):
   seen.append((before,face,after))
   return {'source':'controlled_same_field_case'} if after.startswith('を渡ります') else None
  with patch('semantic_roles.candidate_nominal_spelling_evidence',side_effect=evidence):
   self.assertTrue(K._unresolved_focused_source_nominal(source,first,first+2))
   self.assertFalse(K._unresolved_focused_source_nominal(source,last,last+2))
   self.assertTrue(conflict(source,first,first+4,'橋だけ'))
   self.assertFalse(conflict(source,last,last+4,'橋だけ'))
  self.assertTrue(any(after=='' for before,face,after in seen))
  self.assertTrue(any(after=='を渡ります' for before,face,after in seen))
  self.assertFalse(any('⇒' in before+after for before,face,after in seen))

 def test_existing_complete_phrase_proof_keeps_each_member_boundary(self):
  source='ももとなしだけ';focused=R.native_focused_nominal_parts(source)
  self.assertIsNotNone(focused)
  self.assertEqual(focused[0],5)
  parts=M.tokenize(source);members=set()
  K._lexical_units(source,parts,members)
  self.assertIn((0,2),members);self.assertIn((3,5),members)
  self.assertNotIn((0,7),members)
  self.assertFalse(any(a<3 and b>2 for a,b in members))

 def test_source_suffix_inside_a_word_cannot_be_an_invented_focus(self):
  for source in ('はしだけど','はしばかりか','はしなどと','はしたけ'):
   self.assertIsNone(R.native_focused_nominal_parts(source),source)
   members=set();K._lexical_units(source,M.tokenize(source),members)
   # This review checks the new whole-field proof, not every older path.
   actual=R.native_focused_nominal_parts
   with patch.object(R,'native_focused_nominal_parts',side_effect=lambda text: None if text==source else actual(text)):
    fallback=set();K._lexical_units(source,M.tokenize(source),fallback)
   self.assertEqual(members,fallback,source)

if __name__=='__main__':unittest.main()
