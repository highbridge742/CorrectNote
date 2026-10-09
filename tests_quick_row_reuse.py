# -*- coding: utf-8 -*-
"""Unedited Quick rows retain all input evidence and never reuse live edits."""
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import quick_analysis as Q,analysis_work_app as work,quick_row_reuse as reuse
from analysis_work import Document,Occurrence,Calculation
import tests_quick_async as quick_tests


class QuickRowReuseTests(unittest.TestCase):
    setUp=quick_tests.QuickAsyncTests.setUp

    def complete(self,text='一行目\n二行目\n三行目'):
        self.widget.text=text;Q.start(self.app)
        task=self.worker.submit.call_args[0][0]
        rows=[dict(original=s,corrected=s,analysis_status='complete') for s in task['lines']]
        value=dict(results=rows,units=[[] for _ in rows],corrected_units=[(r['original'],[]) for r in rows])
        self.worker.poll.return_value=value;Q.start(self.app)
        self.worker.poll.return_value=None
        return task,value

    def edit(self,text,edit=None,discard=False):
        self.widget.text=text;work.quick_edited(self.app,text,discard,edit)

    def test_changed_row_is_the_only_row_sent_for_recorrection(self):
        self.complete();self.edit('一行目\n編集済み\n三行目');Q.start(self.app)
        task=self.worker.submit.call_args[0][0]
        self.assertEqual(sorted(task.get('reuse',{})),[0,2])
        self.assertEqual(task['lines'],['一行目','編集済み','三行目'])

    def test_a_b_a_edit_cannot_revive_a_row_before_another_dispatch(self):
        self.complete();self.edit('一行目\n別の行\n三行目');self.edit('一行目\n二行目\n三行目');Q.start(self.app)
        self.assertEqual(sorted(self.worker.submit.call_args[0][0].get('reuse',{})),[0,2])

    def test_newline_edits_drop_shifted_row_slots_and_keep_only_prior_rows(self):
        self.complete();self.edit('一行目\n二\n行目\n三行目');Q.start(self.app)
        self.assertEqual(sorted(self.worker.submit.call_args[0][0].get('reuse',{})),[0])

    def test_live_reading_and_calculation_changes_reanalyze_their_rows(self):
        self.complete('橋を見る\n8*5\n末尾')
        doc=work.quick_document(self.app,self.widget.text)
        self.assertTrue(doc.remember(0,1,'橋','はし'))
        self.assertTrue(doc.remember_calculation(5,8,'8*5','40'))
        Q.start(self.app)
        self.assertEqual(sorted(self.worker.submit.call_args[0][0].get('reuse',{})),[2])

    def test_model_and_attested_state_changes_do_not_reuse_rows(self):
        self.complete();self.app._analysis_state_revision=1;Q.start(self.app)
        self.assertFalse(self.worker.submit.call_args[0][0].get('reuse'))
        self.complete();self.app._attested_surfaces={'新語':1};self.edit(self.widget.text+'末');Q.start(self.app)
        self.assertFalse(self.worker.submit.call_args[0][0].get('reuse'))

    def test_new_owner_and_close_release_the_displayed_result_metadata(self):
        self.complete();self.app._quick_text=quick_tests.Widget(self.widget.text);Q.start(self.app)
        self.assertFalse(self.worker.submit.call_args[0][0].get('reuse'))
        self.app._quick_text=self.widget;self.complete();Q.close(self.app)
        self.assertIsNone(getattr(self.app,'_quick_row_reuse',None))

    def test_discard_or_identical_explicit_edit_invalidates_all_rows(self):
        for discard in (False,True):
            self.app._quick_job=None;self.complete()
            self.edit(self.widget.text,discard=discard);Q.start(self.app)
            self.assertFalse(self.worker.submit.call_args[0][0].get('reuse'))

    def test_unaccepted_worker_result_never_becomes_reusable(self):
        self.widget.text='一行目\n二行目';Q.start(self.app)
        self.edit('一行目\n編集');Q.start(self.app)
        self.assertFalse(self.worker.submit.call_args[0][0].get('reuse'))


class QuickReuseValueTests(unittest.TestCase):
    def task(self):return dict(lines=['原文'],input_method='kana',readings={},calculations={},attested=())
    def test_display_and_dispatch_mutations_do_not_change_the_kept_value(self):
        task=self.task();app=SimpleNamespace();scope=Document(object(),'原文').work(('state',))
        value=dict(results=[dict(original='原文',corrected='結果',analysis_status='complete')],units=[[{'start':0}]],corrected_units=[('結果',[])])
        reuse.remember(app,scope,task,value);value['results'][0]['corrected']='破壊';value['units'][0][0]['start']=9
        first=reuse.select(app,scope,task);self.assertEqual(first[0][1][0]['corrected'],'結果');self.assertEqual(first[0][1][1][0]['start'],0)
        first[0][1][0]['corrected']='再破壊';self.assertEqual(reuse.select(app,scope,task)[0][1][0]['corrected'],'結果')

    def test_incomplete_limited_failed_or_changed_evidence_is_not_reused(self):
        task=self.task()
        for status in ('incomplete','limited',None):
            entry=(reuse.row_key(task,0),(dict(original='原文',analysis_status=status),[],('',[])))
            self.assertIsNone(reuse.restored(dict(task,reuse={0:entry}),0))
        entry=(reuse.row_key(task,0),(dict(original='原文',analysis_status='complete'),[],('',[])))
        for changed in (dict(task,input_method='romaji'),dict(task,lines=['別文']),dict(task,readings={0:(Occurrence(0,2,'原文','げんぶん'),)}),dict(task,calculations={0:(Calculation(0,2,'原文','値'),)})):
            self.assertIsNone(reuse.restored(dict(changed,reuse={0:entry}),0))

    def test_worker_skips_only_completed_matching_rows_and_keeps_result_order(self):
        from analysis_worker import Runtime
        r=Runtime.__new__(Runtime);r.store=Mock();r.tokenize=Mock();r.decisions=None;r.context_vec=None;r.index=None;r.choices=None
        task=dict(lines=['保持','変更',''],input_method='kana',calculations={},readings={})
        result=dict(original='保持',corrected='保持結果',analysis_status='complete')
        task['reuse']={0:(reuse.row_key(task,0),(result,[{'start':0}],('保持結果',[])))}
        def correct(line,*args,**kwargs):return dict(original=line,corrected=line,analysis_status='complete')
        with patch('corrector.correct_line',side_effect=correct) as calls,patch('quote_calculator.apply_to_result',side_effect=lambda result,*a:result),patch('units.build_suspect_units',return_value=('',[])),patch('units.build_line_units',return_value=('',[])):
            value=r.quick(task)
        self.assertEqual([c[0][0] for c in calls.call_args_list],['変更'])
        self.assertEqual(value['results'],[result,dict(original='変更',corrected='変更',analysis_status='complete'),None])
        self.assertEqual(value['units'][0],[{'start':0}]);self.assertEqual(value['corrected_units'][0],('保持結果',[]))

if __name__=='__main__':unittest.main()
