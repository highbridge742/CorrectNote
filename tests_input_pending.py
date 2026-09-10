# -*- coding: utf-8 -*-
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class InputPendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        wanted={'_analyze_chunk','_analyze_if_changed'}
        functions=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in wanted]
        cls.scope={}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'app.py','exec'),cls.scope)

    def test_old_slice_stops_until_input_check(self):
        def forbidden():self.fail('入力確認前に旧解析へ進んだ')
        h=SimpleNamespace(_analyze_job='chunk',_after_id='input-check',_view_changing=forbidden)
        self.scope['_analyze_chunk'](h)
        self.assertIsNone(h._analyze_job)
        self.assertEqual(h._after_id,'input-check')

    def test_same_text_resumes_unfinished_work_without_reanalysis(self):
        calls=[]
        h=SimpleNamespace(_after_id='input-check',editor_source_text=lambda:'same',
            _analyze_text='same',_analyze_pos=1,_analyze_todo=[0,1,2],_analyze_job=None,
            _schedule_analysis_chunk=lambda:calls.append('resume'),
            _analyze=lambda:calls.append('rebuild'))
        self.scope['_analyze_if_changed'](h)
        self.assertEqual(calls,['resume'])
        self.assertIsNone(h._after_id)

    def test_changed_text_rebuilds_instead_of_resuming_old_todo(self):
        calls=[]
        h=SimpleNamespace(_after_id='input-check',editor_source_text=lambda:'new',
            _analyze_text='old',_schedule_analysis_chunk=lambda:calls.append('resume'),
            _analyze=lambda:calls.append('rebuild'))
        self.scope['_analyze_if_changed'](h)
        self.assertEqual(calls,['rebuild'])

    def test_no_pending_input_keeps_existing_chunk_path(self):
        class Entered(Exception):pass
        def entry():raise Entered()
        h=SimpleNamespace(_after_id=None,_view_changing=entry)
        with self.assertRaises(Entered):self.scope['_analyze_chunk'](h)


if __name__=='__main__':unittest.main()
