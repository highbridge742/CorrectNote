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
        import analysis_async
        import analysis_work_app as input_work
        import os
        cls.scope={'analysis_async':analysis_async,'input_work':input_work,'os':os}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'app.py','exec'),cls.scope)

    def test_recent_input_does_not_pause_the_worker_transport(self):
        class Dispatched(Exception):pass
        def dispatch(count):raise Dispatched()
        h=SimpleNamespace(_after_id=None,_view_changing=lambda:False,
            ANALYZE_CHUNK=20,_analyze_units_only=False,_interacting=lambda:True,
            _analyze_slice=dispatch,_schedule_analysis_chunk=lambda:self.fail('idle wait'))
        with self.assertRaises(Dispatched):self.scope['_analyze_chunk'](h)

    def test_held_view_still_defers_projection_even_for_cached_units(self):
        for units in (False,True):
            for overview,drag in ((object(),None),(None,{'mode':'scroll'})):
                calls=[]
                h=SimpleNamespace(_after_id=None,_view_changing=lambda:False,
                    ANALYZE_CHUNK=20,_analyze_units_only=units,
                    _overview=overview,_drag=drag,
                    _analyze_slice=lambda count:self.fail('held view changed'),
                    _schedule_analysis_chunk=lambda:calls.append('defer'))
                self.scope['_analyze_chunk'](h)
                self.assertEqual(calls,['defer'])

    def test_old_slice_stops_until_input_check(self):
        # 入力の確かめが予約中なら旧解析へ進まない。2026-11-17 から続きを予約して待つ（表示準備中で止まらないように・
        # view_prep_watch）。CN_VIEW_PREP_WATCH=0 なら前の形（予約しない）
        import os
        def forbidden():self.fail('入力確認前に旧解析へ進んだ')
        for watch,want in ((None,['chunk queued']),('0',[])):
            saved=os.environ.pop('CN_VIEW_PREP_WATCH',None)
            if watch is not None:os.environ['CN_VIEW_PREP_WATCH']=watch
            try:
                calls=[]
                h=SimpleNamespace(_analyze_job='chunk',_after_id='input-check',_view_changing=forbidden,
                                  _schedule_analysis_chunk=lambda:calls.append('chunk queued'))
                self.scope['_analyze_chunk'](h)
                self.assertIsNone(h._analyze_job)
                self.assertEqual(h._after_id,'input-check')
                self.assertEqual(calls,want)
            finally:
                os.environ.pop('CN_VIEW_PREP_WATCH',None)
                if saved is not None:os.environ['CN_VIEW_PREP_WATCH']=saved

    def test_same_text_resumes_unfinished_work_without_reanalysis(self):
        calls=[]
        h=SimpleNamespace(_after_id='input-check',editor_source_text=lambda:'same',
            settings={'input_method':'kana'},_analyze_text='same',_analyze_pos=1,_analyze_todo=[0,1,2],_analyze_job=None,
            _schedule_analysis_chunk=lambda:calls.append('resume'),
            _analyze=lambda:calls.append('rebuild'))
        h._analyze_dependencies=self.scope['analysis_async'].state_key(h)
        h._analyze_work=self.scope['input_work'].token(h)
        self.scope['_analyze_if_changed'](h)
        self.assertEqual(calls,['resume'])
        self.assertIsNone(h._after_id)

    def test_same_text_with_changed_dependencies_rebuilds(self):
        calls=[]
        h=SimpleNamespace(settings={'input_method':'kana'},_after_id='input-check',
            editor_source_text=lambda:'same',_analyze_text='same',
            _analyze_dependencies=('old',),_analyze=lambda:calls.append('rebuild'))
        self.scope['_analyze_if_changed'](h)
        self.assertEqual(calls,['rebuild'])

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
