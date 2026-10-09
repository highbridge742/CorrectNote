# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""New input must not queue behind an unrelated startup backlog."""
import unittest
from types import SimpleNamespace
import analysis_work_app as W

class InputPriorityTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from session import SessionStore
        self.root=tk.Tk();self.root.withdraw()
        editor=tk.Text(self.root,undo=True)
        self.a=SimpleNamespace(editor=editor,session=SessionStore())
        self.a.session.reset_fresh()
        self.a.editor_source_text=lambda:editor.get('1.0','end-1c')
        editor.insert('1.0','元の行\n正常な行\n末尾の行')
        W.select_document(self.a,self.a.editor_source_text())
        W.install(self.a)
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def test_actual_edit_goes_before_backlog_and_preserves_every_row(self):
        a=self.a;a.editor.insert('3.end','追記')
        todo,changed=W.edited_first(a,[0,1,2])
        self.assertTrue(changed);self.assertEqual(todo,[2,0,1])
        self.assertEqual(a._input_document.text,a.editor_source_text())
    def test_cursor_and_display_projection_do_not_make_new_priority(self):
        a=self.a;a.editor.insert('3.end','追記');generation=W.token(a)
        a.editor.mark_set('insert','1.0')
        with W.display_update(a):a.editor.insert('1.0','表示だけ')
        self.assertEqual(W.token(a),generation)
        self.assertEqual(W.edited_first(a,[0,1,2]),([2,0,1],True))
    def test_completed_row_and_another_generation_keep_pending_order(self):
        a=self.a;a.editor.insert('3.end','追記')
        self.assertEqual(W.edited_first(a,[0,1]),([0,1],False))
        W.select_document(a,a.editor_source_text())
        self.assertEqual(W.edited_first(a,[0,1,2]),([0,1,2],False))
    def test_deleted_newline_prioritizes_joined_row(self):
        a=self.a;a.editor.delete('2.end','3.0')
        self.assertEqual(W.edited_first(a,[0,1]),([1,0],True))

    def test_model_invalidation_keeps_current_edit_first_but_rejects_old_results(self):
        from app import CorrectNoteApp
        for keep in (True,False):
            with self.subTest(keep_current=keep):
                a=self.a;a.editor.insert('3.end','追記');old=W.token(a)
                a._analyze_work=old;a._async_contexts={'old':'value'}
                CorrectNoteApp._invalidate_analysis_cache(a,keep_current=keep)
                self.assertNotEqual(W.token(a),old);self.assertNotEqual(a._analyze_work,W.token(a))
                self.assertEqual(a._async_contexts,{})
                self.assertEqual(W.edited_first(a,[0,1,2]),([2,0,1],True))
    def test_model_invalidation_cannot_revive_an_old_tab_or_edit_priority(self):
        from app import CorrectNoteApp
        a=self.a;a.editor.insert('3.end','追記')
        W.select_document(a,a.editor_source_text())
        CorrectNoteApp._invalidate_analysis_cache(a,keep_current=False)
        self.assertEqual(W.edited_first(a,[0,1,2]),([0,1,2],False))
        a.editor.insert('2.end','入力');old=W.token(a)
        from session import new_tab
        a.session.add_tab(new_tab(text='別の文書'))
        W.select_document(a,a.editor_source_text())
        CorrectNoteApp._invalidate_analysis_cache(a)
        self.assertNotEqual(W.token(a),old)
        self.assertEqual(W.edited_first(a,[0,1,2]),([0,1,2],False))

class WorkerPrewarmTests(unittest.TestCase):
    def test_prewarm_sends_no_unready_state_and_real_request_reuses_process(self):
        from unittest.mock import Mock,patch
        import analysis_async as A
        worker=Mock();worker.process.is_alive.return_value=True
        worker.submit.side_effect=[1,2]
        a=SimpleNamespace()
        with patch.object(A,'Worker',return_value=worker) as factory,patch.object(A,'snapshot',return_value={'entries':[]}) as snapshot,patch.object(A,'state_key',return_value='ready-key'):
            A.prewarm(a);A.prewarm(a)
            factory.assert_called_once_with();snapshot.assert_not_called()
            worker.submit.assert_called_once_with({'kind':'warmup'})
            A._request(a,{'kind':'prepare','lines':['資料']},'scope')
            snapshot.assert_called_once_with(a)
            self.assertEqual(worker.submit.call_args.args,({'kind':'prepare','lines':['資料']},{'entries':[],'_state_identity':'ready-key'}))
            self.assertIs(a._correction_worker,worker)
            self.assertEqual(a._async_request,('scope',2))
            self.assertEqual(a._worker_state,'ready-key')
    def test_close_does_not_start_prewarm(self):
        from unittest.mock import patch
        import analysis_async as A
        with patch.object(A,'Worker') as factory:
            A.prewarm(SimpleNamespace(_closing=True))
            factory.assert_not_called()
    def test_failed_submission_closes_only_its_new_worker_and_can_retry_normally(self):
        from unittest.mock import Mock,patch
        import analysis_async as A
        worker=Mock();worker.submit.side_effect=OSError('transport failed')
        a=SimpleNamespace()
        with patch.object(A,'Worker',return_value=worker),patch.object(A.traceback,'print_exc') as report:
            A.prewarm(a)
            worker.close.assert_called_once_with();report.assert_called_once_with()
            self.assertFalse(hasattr(a,'_correction_worker'))

class PreparedContextResumeTests(unittest.TestCase):
    def test_superseded_preparation_keeps_only_complete_reusable_line_values(self):
        from tests_analysis_async import initial
        from analysis_worker import Runtime,snapshot
        from analysis_context import request_scope,SupersededAnalysis
        state=snapshot(initial());lines=['確認用の資料です。','今日は晴れです。','次の文章です。']
        expected=Runtime();expected.set_state(state);complete=expected.prepare(lines)
        for stop in (2,5):
            runtime=Runtime();runtime.set_state(state);checks=[]
            def cancelled():checks.append(True);return len(checks)==stop
            with self.subTest(stop=stop),request_scope(cancelled):
                with self.assertRaises(SupersededAnalysis):runtime.prepare(lines)
            self.assertFalse(runtime.prepared)
            self.assertEqual(runtime.prepare(lines),complete)

class WorkerEarlyCloseTests(unittest.TestCase):
    def test_close_before_first_document_stops_the_prewarmed_process(self):
        import analysis_async as A
        a=SimpleNamespace()
        try:
            A.prewarm(a)
            worker=a._correction_worker
            self.assertTrue(worker.process.is_alive())
            self.assertIsNone(a._worker_state)
            A.close(a)
            self.assertFalse(worker.process.is_alive())
        finally:A.close(a)

if __name__=='__main__':unittest.main()
