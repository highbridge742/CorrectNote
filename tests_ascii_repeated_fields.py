# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

class AsciiRepeatedFieldsTests(unittest.TestCase):
 def setUp(self):
  from tests_analysis_async import initial
  from last_choice import set_active
  import public_nominal_cache as P
  self.assertTrue(P.available())
  self.a=initial();self.addCleanup(set_active,None)
 def run_line(self,s,mode):
  from correction_entry import correct_line
  return correct_line(s,self.a.store,input_method=mode,dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None)
 def test_same_keys_in_three_fields_keep_only_the_original_code_protected(self):
  for mode,raw in (('kana','d).ek-c@y'),('romaji','shoruiwohozonshimasu')):
   with self.subTest(mode=mode):
    free=self.run_line(raw,mode)['corrected'];self.assertNotEqual(free,raw)
    code='💡 fn( '+raw+' ) ©';source='👩🏽‍💻 '+raw+'\t'+code+'\t'+raw
    row=self.run_line(source,mode)
    self.assertEqual(row['corrected'],'👩🏽‍💻 '+free+'\t'+code+'\t'+free)
    self.assertEqual(row['odd_spans'],[]);self.assertEqual(row['analysis_status'],'complete')
    spans=row['original_spans'];a=source.index(raw);z=source.rindex(raw)
    self.assertEqual(spans,[(a,a+len(raw)),(z,z+len(raw))])
 def test_ancestor_same_substring_is_located_in_its_real_field(self):
  import corrector as C
  raw='d).ek-c@y';original=raw+'\t💡 fn( '+raw+' ) ©\t'+raw
  current='しょるいの保存\t💡 fn( しょるいの保存 ) ©\tしょるいの保存'
  token=C._CORRECTION_PATH.set((original,))
  try:
   pos=current.index('しょるいの保存',current.index('\t')+1)
   accepted,reason=C._check_replacement(current,(pos,pos+len('しょるいの保存'),'書類の保存','かな入力'),None,None)
   self.assertIsNone(accepted);self.assertEqual(reason,'original_ascii_expression')
  finally:C._CORRECTION_PATH.reset(token)
 def test_only_whitespace_detached_outer_symbols_can_be_removed(self):
  import halfwidth as H
  raw='d).ek-c@y'
  for s in ('💡\u0301 fn( '+raw+' )','💡fn( '+raw+' )','💡 fn( © '+raw+' )','💡 関数( '+raw+' )'):
   a=s.index(raw);self.assertFalse(H.original_ascii_expression(s,a,a+len(raw)),s)

if __name__=='__main__':unittest.main()
