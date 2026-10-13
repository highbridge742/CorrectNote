import unittest
from unittest.mock import patch
import halfwidth as H

RAW='d).ek-c@y'

class AsciiSymbolSourceTests(unittest.TestCase):
 def proof(self,line,raw=RAW):
  start=line.index(raw)
  return H.original_ascii_expression(line,start,start+len(raw))

 def test_detached_edges_keep_actual_call_assignment_and_operator(self):
  for skeleton in ('fn( '+RAW+' )','obj . '+RAW,'value = '+RAW,
                   'value == '+RAW,'values[ '+RAW+' ]',RAW+' = 1;'):
   for left,right in (('💡 ',''),('',' ©'),('💡 👩🏽‍💻 ',' © 💡')):
    with self.subTest(skeleton=skeleton,left=left,right=right):
     self.assertTrue(self.proof(left+skeleton+right))
  full=''.join(chr(ord(c)+0xfee0) if 0x21<=ord(c)<=0x7e else c for c in RAW)
  self.assertTrue(self.proof('👩🏽‍💻 ｆｎ（ '+full+' ） 💡',full))
  self.assertTrue(self.proof('💡 fn( shoruiwohozonshimasu )','shoruiwohozonshimasu'))

 def test_internal_attached_combining_and_natural_words_are_not_discarded(self):
  for source in ('fn( 💡 '+RAW+' )','💡 fn( © '+RAW+' )',
                 '💡print( '+RAW+' )','print( '+RAW+' )💡',
                 '💡\u0301 print( '+RAW+' )','💡 説明( '+RAW+' )',
                 '説明 💡 print( '+RAW+' )','💡 ( '+RAW+' )',
                 '💡 '+RAW,'💡 unknown '+RAW,'💡 C:\\Notes\\'+RAW,
                 '💡 https://example.test/'+RAW):
   with self.subTest(source=source):self.assertFalse(self.proof(source))

 def test_original_common_check_keeps_unicode_ancestor_and_partial_scope(self):
  import corrector as C
  source='mojinyuuryoku\t👩🏽‍💻 print( '+RAW+' ) 💡'
  start=source.index(RAW)
  self.assertTrue(H.original_ascii_expression(source,start+2,start+4))
  accepted,reason=C._check_replacement(source,(start,start+len(RAW),'書類の保存','IT・PC操作'),None,None)
  self.assertIsNone(accepted);self.assertEqual(reason,'original_ascii_expression')
  restored='文字入力\t👩🏽‍💻 print( しょるいの保存 ) 💡'
  pos=restored.index('しょるいの保存');token=C._CORRECTION_PATH.set((source,))
  try:
   accepted,reason=C._check_replacement(restored,(pos,pos+len('しょるいの保存'),'書類の保存','かな入力'),None,None)
   self.assertIsNone(accepted);self.assertEqual(reason,'original_ascii_expression')
  finally:C._CORRECTION_PATH.reset(token)
  separate='💡 fn( '+RAW+' )\t'+RAW
  second=separate.rindex(RAW)
  self.assertFalse(H.original_ascii_expression(separate,second,second+len(RAW)))


class AsciiSymbolRuntimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from tests_analysis_async import initial
  from last_choice import set_active
  cls.a=initial();cls.addClassCleanup(set_active,None)
 def run_line(self,source,mode='kana'):
  from correction_entry import correct_line
  a=self.a
  return correct_line(source,a.store,input_method=mode,dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
 def test_both_modes_preserve_source_code_and_complete_separate_field(self):
  for mode,raw,first,face in (('kana',RAW,'d).et@ss@gjr','書類が届きます'),
                             ('romaji','shoruiwohozonshimasu','shoruiwohozonshimasu','書類を保存します')):
   code='💡 fn( '+raw+' ) ©';source='👩🏽‍💻 '+first+'\t'+code
   with self.subTest(mode=mode):
    row=self.run_line(source,mode)
    self.assertEqual(row['corrected'],'👩🏽‍💻 '+face+'\t'+code)
    self.assertEqual(row['odd_spans'],[]);self.assertEqual(row['analysis_status'],'complete')
    self.assertEqual(row['original_spans'],[(source.index(first),source.index(first)+len(first))])
  for mode in ('kana','romaji'):
   source='💡 value = '+RAW
   with self.subTest(mode=mode,source=source):self.assertEqual(self.run_line(source,mode)['corrected'],source)
 def test_unrelated_natural_attached_and_literal_paths_keep_old_result(self):
  for source in ('💡 説明( '+RAW+' )','💡'+RAW,
                 '💡 C:\\Notes\\'+RAW,'💡 https://example.test/'+RAW):
   with self.subTest(source=source):
    # All four have no original ASCII structure proof, before or after this change.
    with patch.object(H,'original_ascii_expression',return_value=False):before=self.run_line(source)
    self.assertEqual(self.run_line(source),before)

if __name__=='__main__':unittest.main()
