import unittest
from unittest.mock import patch
from literal_lines import literal_only,unwrapped_only,MAX_ANALYZED_LINE_LENGTH

class LongLiteralRowTests(unittest.TestCase):
 def test_limit_counts_characters_and_preserves_short_normal_text(self):
  n=MAX_ANALYZED_LINE_LENGTH
  for char in ('あ','A','😀'):
   self.assertFalse(literal_only(char*n))
   self.assertFalse(unwrapped_only(char*n))
   self.assertTrue(literal_only(char*(n+1)))
   self.assertTrue(unwrapped_only(char*(n+1)))
  self.assertFalse(literal_only('あ'*3000+'\n'+'あ'*3000))
  self.assertFalse(unwrapped_only('あ'*3000+'\n'+'あ'*3000))
  self.assertTrue(unwrapped_only('x'*4001+'\r'))
  self.assertTrue(literal_only('x'*4001+'\r'))
  self.assertTrue(unwrapped_only('data:image/png;base64,AA=='))
  self.assertFalse(unwrapped_only('https://example.test/'))
 def test_long_row_skips_nlp_without_truncating_text(self):
  from correction_entry import correct_line
  text='日本語も英語も含む ABC 123 😀 '*300
  # The public correction entry must decide before touching supplied stores.
  with patch('corrector.make_tokenizer',side_effect=AssertionError('NLP not required')):
   result=correct_line(text,None)
  self.assertEqual(result['original'],text)
  self.assertEqual(result['corrected'],text)
  self.assertFalse(result['changed'])
  self.assertEqual(result['analysis_status'],'complete')
  self.assertFalse(result['odd_spans'])

 def test_long_tab_rows_do_not_measure_every_segment(self):
  import app
  with patch('tkinter.font.Font',side_effect=AssertionError('unbounded tab measurement')):
   self.assertEqual(app.CorrectNoteApp._line_tab_stops(None,None,'word\t'*3000),())

 def test_direct_equal_does_not_start_quote_in_long_or_data_rows(self):
  from types import SimpleNamespace as N
  from unittest.mock import Mock
  import app
  for row in ('x'*4000,'x'*4001,'data:,abc'):
   editor=Mock();editor.get.return_value=row
   a=N(editor=editor,_pick_mode=None,_start_pick_mode=Mock())
   self.assertIsNone(app.CorrectNoteApp._on_equal_key(a,N(char='=')))
   editor.insert.assert_not_called();a._start_pick_mode.assert_not_called()
  a=N(_pick_mode=object(),_end_pick_mode=Mock())
  self.assertIsNone(app.CorrectNoteApp._on_equal_key(a,N(char='=')))
  a._end_pick_mode.assert_called_once_with(keep_equals=True)

 def test_ctrl_edges_skip_tokenizer_only_for_bounded_display_rows(self):
  from types import SimpleNamespace as N
  from unittest.mock import Mock
  import app
  for text,skipped in (('x'*4001,True),('data:,abc',True),('ordinary text',False)):
   tokenize=Mock(return_value=[]);widget=Mock();widget.get.return_value=text
   widget.compare.return_value=False
   a=N(store=N(_tokenize_fn=tokenize),_move_text_cursor=Mock())
   event=N(widget=widget,state=1)
   with patch.object(app,'_python_text_position',return_value=(1,1)):
    self.assertEqual(app.CorrectNoteApp._move_text_edge(a,event,1),'break')
   if skipped:tokenize.assert_not_called()
   else:tokenize.assert_called_once_with(text)
   self.assertIs(a._move_text_cursor.call_args[0][0],event)
   widget.insert.assert_not_called();widget.delete.assert_not_called()

if __name__=='__main__':unittest.main()
