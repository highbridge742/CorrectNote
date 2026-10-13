from unittest.mock import patch
import unittest
import corrector as C
import ime_spelling as I
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active
from analysis_context import SupersededAnalysis

DOC='d).et@ss@gjr';PERSON='t@hpet@fudjr';READING='しょるいがとどきます';FACE='書類が届きます'

class JISDetachedSymbolTests(unittest.TestCase):
 def setUp(self):
  self.a=initial();self.addCleanup(set_active,None)
 def run_line(self,text,mode='kana'):
  a=self.a
  return correct_line(text,a.store,input_method=mode,dict_index=a.dict_index,
   decisions=a.decisions,context_vec=None)
 def finish(self,text):
  a=self.a;start=text.index(DOC)
  return C._finish_halfwidth_candidate(text,start,start+len(DOC),READING,a.store,
   C.make_tokenizer(a.store),a.dict_index,a.decisions,input_method='kana',native_context_required=True)

 def test_multiple_edge_symbols_keep_original_unicode_ranges(self):
  prefix='💡 👩🏽‍💻 ';source=prefix+DOC+' ©'
  result=self.run_line(source)
  self.assertEqual(result['corrected'],prefix+FACE+' ©')
  self.assertEqual(result['original_spans'],[(len(prefix),len(prefix)+len(DOC))])
  self.assertEqual(result['spans'],[(len(prefix),len(prefix)+len(FACE))])
  self.assertEqual(result['odd_spans'],[])

 def test_original_partial_block_precedes_projection_after_shortened_field(self):
  source=PERSON+'\t👩‍💻 '+DOC;self.a.decisions.protect('ss@g')
  with patch.object(I,'project_first_words',wraps=I.project_first_words) as projected:
   result=self.run_line(source)
  self.assertEqual(result['corrected'],'学生が話します\t👩‍💻 '+DOC)
  self.assertNotIn(READING,[call.args[0] for call in projected.call_args_list])
  self.assertEqual(result['original_spans'],[(0,len(PERSON))])

 def test_final_original_common_gate_rechecks_whole_source(self):
  source='👩🏽‍💻 '+DOC+' 💡';gate=C._check_replacement;calls=[]
  def checked(line,edit,*args,**kwargs):
   calls.append((line,edit))
   if line==source and edit[2]==FACE:return None,'forced_final_original'
   return gate(line,edit,*args,**kwargs)
  with patch.object(C,'_check_replacement',side_effect=checked):
   self.assertIsNone(self.finish(source))
  expected=(source.index(DOC),source.index(DOC)+len(DOC))
  self.assertIn((source,(*expected,READING,'IT・PC操作')),calls)
  self.assertIn((source,(*expected,FACE,'IT・PC操作')),calls)

 def test_original_pair_rejection_keeps_detached_input(self):
  source='👩‍💻 '+DOC;self.a.decisions.reject(DOC,FACE)
  self.assertEqual(self.run_line(source)['corrected'],source)

 def test_ascii_connectors_and_unseparated_symbols_remain_in_native_input(self):
  for source in ('💡 fn( 👩‍💻 '+DOC+' )','💡 value == '+DOC,
   '💡 （'+DOC+'）','💡'+DOC,'💡 '+DOC+'©','💡 unknown '+DOC):
   with self.subTest(source=source),patch.object(I,'project_first_words',return_value=None) as projected:
    self.assertIsNone(self.finish(source))
    if projected.called:
     self.assertNotEqual(projected.call_args.args[0],READING)

 def test_cancel_and_outer_limit_keep_original_source_state(self):
  source='💡 👩‍💻 '+DOC
  with patch.object(I,'project_first_words',side_effect=SupersededAnalysis()):
   with self.assertRaises(SupersededAnalysis):self.run_line(source)
  self.assertIsNone(C._CORRECTION_SOURCE.get());self.assertEqual(C._CORRECTION_PATH.get(),())
  for exception,reason in ((C._CorrectionLimit,'depth_limit'),(C._CorrectionCycle,'cycle')):
   with self.subTest(reason=reason),patch.object(I,'project_first_words',side_effect=exception()):
    row=self.run_line(source)
   self.assertEqual(row['corrected'],source);self.assertEqual(row['analysis_status'],'incomplete')
   self.assertEqual(row['stop_reason'],reason);self.assertEqual(row['original_spans'],[])
  self.assertIsNone(C._CORRECTION_SOURCE.get());self.assertEqual(C._CORRECTION_PATH.get(),())

 def test_other_column_original_anomaly_is_not_discarded(self):
  # This unconverted field supplies its own anomaly evidence. Compare its
  # original positions after a preceding, independently completed field.
  phrase='処理がじゃのになっていないだろうか';prefix='👩‍💻 '+DOC+'\t'
  before=self.run_line(phrase);source=prefix+phrase
  after=self.run_line(source)
  self.assertTrue(before['odd_spans'])
  self.assertEqual(after['odd_spans'],[(a+len(prefix),b+len(prefix)) for a,b in before['odd_spans']])
  self.assertEqual(after['analysis_status'],before['analysis_status'])
  expected_reports=[dict(report,start=report['start']+len(prefix),end=report['end']+len(prefix))
   for report in before['diagnosis']['search_reports']]
  self.assertEqual(after['diagnosis']['search_reports'],expected_reports)
  self.assertEqual(after['corrected'],'👩‍💻 '+FACE+'\t処理がじゃのになっていないだろうか')

if __name__=='__main__':unittest.main()
