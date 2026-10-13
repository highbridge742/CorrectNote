# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import tests_gui_editing as fixtures

class JISSymbolsTkTests(unittest.TestCase):
 setUp=fixtures.HalfwidthAutofixTkTests.setUp
 tearDown=fixtures.HalfwidthAutofixTkTests.tearDown

 def test_unicode_typed_ranges_and_real_worker_undo_redo(self):
  from analysis_worker import Runtime,snapshot
  import analysis_async,analysis_work_app,ime_watch
  a=self.a;a.settings['input_method']='kana'
  raw='d).et@ss@gjr';face='書類が届きます'
  for prefix,suffix in [('👩‍💻 ',' 💡'),('💡 👩🏽‍💻 ',' ©')]:
   with self.subTest(prefix=prefix):
    a.editor.delete('1.0','end');a.editor.insert('1.0',prefix+suffix)
    a.editor.tag_remove(a.TYPED_TAG,'1.0','end');a._typed_shadow=[prefix+suffix]
    a.editor.insert('1.0+'+str(len(prefix))+'c',raw);a._mark_typed_from_shadow()
    source=prefix+raw+suffix;expected=prefix+face+suffix
    self.assertEqual(a.editor.get('1.0','1.end'),source)
    self.assertEqual(a._typed_ranges_of_row(1),[(len(prefix),len(prefix)+len(raw))])
    a.editor.edit_reset()
    runtime=Runtime();runtime.set_state(snapshot(a))
    value=runtime.execute(dict(kind='line',line=source,input_method='kana',context=[]))
    self.assertEqual(value['result']['corrected'],expected)
    self.assertEqual(value['result']['analysis_status'],'complete')
    a.line_results=[value['result']];analysis_async._unit_values(a,value['result'],value)
    a._analyze_text=source;a._analyze_dependencies=analysis_async.state_key(a)
    a._analyze_work=analysis_work_app.token(a)
    a._ime_comp='';a._ime_first_kana='';a._ime_last_result=''
    with patch.object(ime_watch,'composition_active',return_value=False):
     self.assertTrue(a._apply_unified_autofix())
    self.assertEqual(a.editor.get('1.0','1.end'),expected)
    a.editor.edit_undo();self.assertEqual(a.editor.get('1.0','1.end'),source)
    a.editor.edit_redo();self.assertEqual(a.editor.get('1.0','1.end'),expected)

if __name__=='__main__':unittest.main()
