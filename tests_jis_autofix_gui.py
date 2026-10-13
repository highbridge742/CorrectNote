# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
from tests_gui_editing import HalfwidthAutofixTkTests

class JISAutofixTkTests(unittest.TestCase):
    setUp=HalfwidthAutofixTkTests.setUp
    tearDown=HalfwidthAutofixTkTests.tearDown
    def test_whole_and_mixed_jis_completion_keep_keys_for_undo(self):
        from analysis_worker import Runtime,snapshot
        import analysis_async,analysis_work_app,ime_watch
        a=self.a;a.settings['input_method']='kana'
        for source,expected,start,end in [('d).et@ss@gjr','書類が届きます',0,12),
            ('前文。病気をu6djr。後文。','前文。病気を治します。後文。',6,11)]:
            a.editor.delete('1.0','end');a.editor.insert('1.0',source)
            a.editor.edit_reset();a._typed_shadow=[source]
            a.editor.tag_remove(a.TYPED_TAG,'1.0','end')
            a.editor.tag_add(a.TYPED_TAG,'1.'+str(start),'1.'+str(end))
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
