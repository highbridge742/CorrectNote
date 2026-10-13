import unittest
from unittest.mock import patch

RAW='d).ek-c@y'

class AsciiSourceStructureTests(unittest.TestCase):
 def proof(self,line,raw=RAW,which=0):
  from halfwidth import original_ascii_expression
  start=line.index(raw,which)
  return original_ascii_expression(line,start,start+len(raw))

 def test_written_call_attribute_and_operators(self):
  for text in ('print( '+RAW+' )','f( '+RAW+' )','fn ( '+RAW+' )',
   'outer(inner( '+RAW+' ))','obj . '+RAW,'value = '+RAW,
   'value == '+RAW,RAW+' = 1;', 'values[ '+RAW+' ]'):
   with self.subTest(text=text):self.assertTrue(self.proof(text))

 def test_jis_symbols_and_bare_parentheses_are_not_code(self):
  for text in (RAW,'( '+RAW+' )','['+RAW+']', 'メモ '+RAW,
   '資料は'+RAW, 'メモ( '+RAW+' )','ここに( '+RAW+' )',
   'unknown '+RAW,RAW+'。print( value )'):
   with self.subTest(text=text):self.assertFalse(self.proof(text))
  from halfwidth import original_ascii_expression
  for raw in ('md[ki)4l)h','md@i(4l)h','hd(4r.bsw@','2;\\]'):
   self.assertFalse(original_ascii_expression(raw,0,len(raw)))

 def test_original_field_and_width_boundaries(self):
  for sep in ('\t','⇒','→','。','！？'):
   line='print( '+RAW+' )'+sep+RAW
   self.assertTrue(self.proof(line));self.assertFalse(self.proof(line,which=line.rindex(RAW)))
  full=''.join(chr(ord(c)+0xFEE0) if 0x21<=ord(c)<=0x7e else c for c in RAW)
  self.assertTrue(self.proof('ｆｎ（ '+full+' ）',full))
  from halfwidth import original_ascii_expression
  for text in ('print( 日本語 )','obj . 書類','value = 資料'):
   start=text.index('日本語') if '日本語' in text else len(text)-2
   self.assertFalse(original_ascii_expression(text,start,len(text)))

 def test_common_check_preserves_original_ancestor(self):
  import corrector as C
  rawline='print( '+RAW+' )';restored='print( しょるいの保存 )'
  a=rawline.index(RAW)
  direct,reason=C._check_replacement(rawline,(a,a+len(RAW),'書類の保存','IT・PC操作'),None,None)
  self.assertIsNone(direct);self.assertEqual(reason,'original_ascii_expression')
  token=C._CORRECTION_PATH.set((rawline,))
  try:
   direct,reason=C._check_replacement(restored,(a,a+len('しょるいの保存'),'書類の保存','かな入力'),None,None)
   self.assertIsNone(direct);self.assertEqual(reason,'original_ascii_expression')
  finally:C._CORRECTION_PATH.reset(token)

 def test_partial_original_ranges_are_covered(self):
  from halfwidth import original_ascii_expression
  line='prefix = '+RAW
  a=line.index(RAW)
  self.assertTrue(original_ascii_expression(line,a+2,a+4))
  self.assertFalse(original_ascii_expression(RAW,2,4))

class AsciiSourceRuntimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from tests_analysis_async import initial
  from last_choice import set_active
  cls.a=initial();cls.addClassCleanup(set_active,None)

 def run_line(self,text,mode='kana'):
  from correction_entry import correct_line
  a=self.a
  return correct_line(text,a.store,context_vocab={},input_method=mode,
   decisions=a.decisions,dict_index=a.dict_index,context_vec=a.context_vec)

 def test_source_code_scope_and_separate_completion(self):
  for mode in ('kana','romaji'):
   line='print( '+RAW+' )'
   result=self.run_line(line,mode)
   self.assertEqual(result['corrected'],line);self.assertEqual(result['odd_spans'],[])
   self.assertEqual(result['analysis_status'],'complete')
  line='print( '+RAW+' )\td).et@ss@gjr'
  result=self.run_line(line)
  self.assertEqual(result['corrected'],'print( '+RAW+' )\t書類が届きます')
  self.assertEqual(result['original_spans'],[(len('print( '+RAW+' )\t'),len(line))])
  self.assertEqual(result['odd_spans'],[]);self.assertEqual(result['analysis_status'],'complete')

 def test_legacy_keys_remain_and_blocked_source_stays(self):
  from unittest.mock import patch
  self.assertEqual(self.run_line(RAW)['corrected'],'書類の保存')
  self.assertEqual(self.run_line('md[ki)4l)h')['corrected'],'文字入力')
  a=self.a;original=a.decisions.blocks
  def block(source,target):return RAW in source or original(source,target)
  with patch.object(a.decisions,'blocks',side_effect=block):
   self.assertEqual(self.run_line(RAW)['corrected'],RAW)

 def test_japanese_parenthesis_has_no_new_code_protection(self):
  import halfwidth as H
  for line in ('メモ( '+RAW+' )','ここに( '+RAW+' )'):
   with patch.object(H,'original_ascii_expression',return_value=False):before=self.run_line(line)
   after=self.run_line(line)
   self.assertEqual(after,before)

if __name__=='__main__':unittest.main()
