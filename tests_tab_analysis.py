# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from analysis_work import Document
import analysis_work_app as work
from analysis_worker import state_key
from session import new_tab,SessionStore
import tab_analysis

class CompletedTabTests(unittest.TestCase):
    def setUp(self):
        self.a=SimpleNamespace(session=SessionStore(),settings={'input_method':'kana'},
            store=SimpleNamespace(revision=lambda:0),_analysis_state_revision=0)
        self.a.session.tabs=[new_tab(text='資料です。'),new_tab(text='別の資料です。')]
        self.select(0)
    def select(self,index):
        a=self.a;a.session.active=index;text=a.session.tabs[index]['text']
        work.select_document(a,text)
        a._analyze_text=text;a._prev_lines=text.split('\n')
        a._analyze_todo=[];a._analyze_pos=0;a._analyze_work=work.token(a)
        a._analyze_dependencies=state_key(a);a._analyze_readings=a._input_document.occurrences
        a.line_results=[dict(original=line,corrected=line) for line in a._prev_lines]
        a._units_cache={(line,line):(line,[]) for line in a._prev_lines}
        a._suspect_units_cache={(line,line,False):(line,[]) for line in a._prev_lines}
        a._analyze_ctx={};a._attested_surfaces={};a._line_words_cache={}
    def test_completed_readings_are_reused_only_in_the_same_live_document(self):
        a=self.a;a._input_document.remember(0,2,'資料','しりょう')
        a._analyze_readings=a._input_document.occurrences
        self.assertTrue(tab_analysis.remember(a))
        self.select(1);self.assertIsNone(tab_analysis.completed(a,'資料です。'))
        self.select(0);self.assertIsNotNone(tab_analysis.completed(a,'資料です。'))
        a._input_document.remember(0,2,'資料','しりお')
        self.assertIsNone(tab_analysis.completed(a,'資料です。'))
    def test_changed_dependencies_and_new_text_reject_completed_values(self):
        a=self.a;tab_analysis.remember(a)
        a._analysis_state_revision+=1
        self.assertIsNone(tab_analysis.completed(a,'資料です。'))
        self.select(0);tab_analysis.remember(a)
        self.assertIsNone(tab_analysis.completed(a,'資料を送ります。'))
    def test_pending_error_and_old_request_values_are_not_cached(self):
        a=self.a
        for flag in ('pending','analysis_error'):
            a.line_results[0][flag]=True
            self.assertFalse(tab_analysis.remember(a));a.line_results[0].pop(flag)
        a.line_results[0]['analysis_status']='incomplete'
        self.assertFalse(tab_analysis.remember(a))
        a.line_results[0].pop('analysis_status')
        a._work_epoch+=1
        self.assertFalse(tab_analysis.remember(a))
    def test_closed_owner_is_pruned_even_when_a_new_tab_has_identical_text(self):
        a=self.a;tab_analysis.remember(a);old_owner=work.owner(a)
        a.session.tabs[0]=new_tab(text='資料です。');self.select(0)
        self.assertIsNone(tab_analysis.completed(a,'資料です。'))
        self.assertNotIn(old_owner,a._completed_tabs)
    def test_existing_line_budget_limits_completed_documents(self):
        a=self.a
        with patch('analysis_cache.MAX_CACHED_LINES',1):
            tab_analysis.remember(a);self.select(1);tab_analysis.remember(a)
            self.assertEqual(len(a._completed_tabs),1)
            self.assertIsNotNone(tab_analysis.completed(a,'別の資料です。'))
    def test_background_partial_values_survive_epoch_but_old_request_is_invalid(self):
        a=self.a;owner=work.owner_for_tab(a,a.session.tabs[1])
        state=dict(owner=owner,text='別の資料です。',readings=(),dependencies=state_key(a),work_epoch=a._work_epoch)
        self.assertTrue(work.background_valid(a,state))
        a._work_epoch+=1
        self.assertFalse(work.background_valid(a,state))
        self.assertTrue(tab_analysis.background_compatible(a,state))
        a._analysis_state_revision+=1
        self.assertFalse(tab_analysis.background_compatible(a,state))
    def test_moved_readings_do_not_invalidate_distant_unchanged_lines(self):
        a=self.a;previous=['冒頭の注釈','資料です。','末尾']
        old=Document(work.owner(a),'\n'.join(previous));old.remember(6,8,'資料','しりょう')
        self.assertTrue(old.occurrences)
        a._analyze_readings=old.occurrences
        a._input_documents[work.owner(a)]=old;a._input_document=old
        current=['冒頭','資料です。','末尾'];old.update('\n'.join(current))
        self.assertEqual(tab_analysis.changed_reading_rows(a,previous,current,0,2),[])
        a._analyze_readings=old.occurrences
        old.remember(3,5,'資料','しりお')
        self.assertEqual(tab_analysis.changed_reading_rows(a,current,current,3,0),[1])

if __name__=='__main__':unittest.main()