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
    def test_closed_tab_releases_all_owner_specific_analysis(self):
        a=self.a;old_tab=a.session.tabs[0];tab_analysis.remember(a);old_owner=work.owner(a)
        a._fg_parked={old_owner:dict(text='資料です。')}
        a._bg_parked={old_owner:dict(text='資料です。')}
        a.session.tabs.pop(0);a.session.active=0
        tab_analysis.forget_closed(a)
        for name in ('_completed_tabs','_fg_parked','_bg_parked','_input_documents'):
            self.assertNotIn(old_owner,getattr(a,name))
        self.assertNotIn(id(old_tab),a._work_tab_owners)

    def test_disk_line_budget_does_not_evict_open_documents(self):
        a=self.a
        with patch('analysis_cache.MAX_CACHED_LINES',1):
            tab_analysis.remember(a);self.select(1);tab_analysis.remember(a)
            self.assertEqual(len(a._completed_tabs),2)
            self.assertIsNotNone(tab_analysis.completed(a,'別の資料です。'))
            self.select(0)
            self.assertIsNotNone(tab_analysis.completed(a,'資料です。'))
    def _remember_background(self,index):
        a=self.a;text=a.session.tabs[index]['text'];lines=text.split('\n')
        return tab_analysis.remember_background(a,dict(owner=work.owner_for_tab(a,a.session.tabs[index]),text=text,
            results=[dict(original=line,corrected=line) for line in lines],ctx={},words={},attested={},
            units={(line,line):(line,[]) for line in lines},suspect_units={(line,line,False):(line,[]) for line in lines},
            dependencies=state_key(a),readings=(),calculations=()))

    def test_background_keeps_every_open_document(self):
        a=self.a;a.session.tabs.extend([new_tab(text='遠い資料です。'),new_tab(text='最後の資料です。')])
        with patch('analysis_cache.MAX_CACHED_LINES',2):
            tab_analysis.remember(a)
            for index in (1,2,3):self.assertTrue(self._remember_background(index))
            self.assertEqual(len(a._completed_tabs),4)
            for tab in a.session.tabs:
                owner=work.owner_for_tab(a,tab)
                self.assertTrue(tab_analysis.display_ready(tab_analysis.completed(a,tab['text'],owner)))
        a._prev_active=2
        self.assertEqual(tab_analysis.prefetch_order(a),[1,2,3])

    def test_large_and_distant_open_documents_are_retained(self):
        a=self.a;a.session.tabs[1]['text']='\n'.join('本文%d。'%i for i in range(1538))
        a.session.tabs.append(new_tab(text='遠い資料です。'))
        with patch('analysis_cache.MAX_CACHED_LINES',2):
            tab_analysis.remember(a);self.assertTrue(self._remember_background(1))
            self.assertTrue(self._remember_background(2))
            self.assertEqual(len(a._completed_tabs),3)
            for index in (1,2):
                tab=a.session.tabs[index];owner=work.owner_for_tab(a,tab)
                saved=tab_analysis.completed(a,tab['text'],owner)
                self.assertTrue(tab_analysis.display_ready(saved))
                self.assertEqual(len(saved['results']),len(tab['text'].split('\n')))

    def test_1538_line_partial_tab_resumes_at_first_unfinished_row(self):
        # The reported screen showed 42/1538 rows while changing tabs.
        a=self.a;lines=['本文%d。'%i for i in range(1538)]
        text='\n'.join(lines);a.session.tabs[1]['text']=text;self.select(1)
        owner=work.owner(a)
        complete=[dict(original=line,corrected=line) for line in lines[:42]]
        units={(line,line):(line,[]) for line in lines[:42]}
        suspect={(line,line,False):(line,[]) for line in lines[:42]}
        tab_analysis.park_background(a,dict(
            owner=owner,text=text,lines=lines,results=complete+[None]*1496,
            ctx={},words={},attested={},units=units,suspect_units=suspect,
            dependencies=state_key(a),readings=(),calculations=(),work_epoch=a._work_epoch))
        self.assertEqual(a._bg_parked[owner]['pos'],42)
        self.select(0);self.select(1)
        a._blank_result=lambda line:dict(original=line,corrected=line,pending=True)
        tab_analysis.restore_previous(a,text,lines)
        self.assertEqual(work.owner(a),owner)
        self.assertEqual(a.line_results[:42],complete)
        self.assertEqual(a._analyze_todo,list(range(42,1538)))
        self.assertEqual(a._analyze_text,text)

    def test_background_request_survives_unrelated_edits_but_not_dependency_changes(self):
        a=self.a;owner=work.owner_for_tab(a,a.session.tabs[1])
        state=dict(owner=owner,text='別の資料です。',readings=(),dependencies=state_key(a),work_epoch=a._work_epoch)
        self.assertTrue(work.background_valid(a,state))
        a._work_epoch+=1
        self.assertTrue(work.background_valid(a,state))
        a.session.tabs[1]['text']='変更後の資料です。'
        self.assertFalse(work.background_valid(a,state))
        a.session.tabs[1]['text']=state['text']
        a._analysis_state_revision+=1
        self.assertFalse(work.background_valid(a,state))
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

    def test_explicit_calculation_invalidates_value_cache_and_stays_in_its_owner(self):
        a=self.a;a.session.tabs[0]['text']='12+3';self.select(0)
        self.assertTrue(tab_analysis.remember(a))
        doc=a._input_document;doc.remember_calculation(0,4,'12+3','15')
        self.assertIsNone(tab_analysis.completed(a,'12+3'))
        self.assertFalse(tab_analysis.remember(a))
        a._analyze_calculations=doc.calculations
        a.line_results=[dict(original='12+3',corrected='15')]
        self.assertTrue(tab_analysis.remember(a))
        self.assertIsNotNone(tab_analysis.completed(a,'12+3'))
        a._analysis_cache={'12+3':a.line_results}
        a._analysis_cache_dependencies={'12+3':state_key(a)}
        self.assertIsNone(tab_analysis.text_results(a,'12+3'))
        a.session.tabs[1]['text']='12+3';self.select(1)
        self.assertIsNone(tab_analysis.completed(a,'12+3'))

    def test_calculation_removal_invalidates_only_its_unchanged_row(self):
        a=self.a;previous=['注記','12+3','末尾']
        doc=Document(work.owner(a),'\n'.join(previous));doc.remember_calculation(3,7,'12+3','15')
        a._input_documents[work.owner(a)]=doc;a._input_document=doc
        a._analyze_readings=();a._analyze_calculations=doc.calculations
        doc.update(doc.text,discard_readings=True)
        self.assertEqual(tab_analysis.changed_reading_rows(a,previous,previous,3,0),[1])

    def test_background_values_compare_calculations_independently_of_readings(self):
        a=self.a;a.session.tabs[1]['text']='12+3';self.select(1)
        doc=a._input_document;doc.remember_calculation(0,4,'12+3','15')
        state=dict(owner=work.owner(a),text='12+3',readings=(),calculations=doc.calculations,
            dependencies=state_key(a),work_epoch=a._work_epoch)
        self.select(0)
        self.assertTrue(work.background_valid(a,state))
        state['calculations']=()
        self.assertFalse(work.background_valid(a,state))


    def test_dirty_tab_restores_old_inputs_for_differential_validation(self):
        a=self.a;old_text='資料です。\n末尾'
        a.session.tabs[0]['text']=old_text;self.select(0)
        doc=a._input_document;doc.remember(0,2,'資料','しりょう')
        a._analyze_readings=doc.occurrences;tab_analysis.remember(a)
        old=doc.occurrences;doc.update('冒頭\n'+old_text)
        a._blank_result=lambda line:dict(original=line,corrected=line,pending=True)
        tab_analysis.restore_previous(a,doc.text,doc.text.split('\n'))
        self.assertEqual(a._prev_lines,old_text.split('\n'))
        self.assertEqual(a._analyze_readings,old)
        self.assertNotEqual(a._analyze_readings,doc.occurrences)
        self.assertEqual(tab_analysis.changed_reading_rows(a,a._prev_lines,doc.text.split('\n'),0,2),[])
        self.assertIsNone(tab_analysis.completed(a,doc.text))

    def test_dirty_tab_rejects_another_owner_or_changed_model(self):
        a=self.a;tab_analysis.remember(a);self.select(1)
        self.assertIsNone(tab_analysis.previous_values(a,work.owner(a)))
        self.select(0);a._analysis_state_revision+=1;a._prev_lines=[]
        tab_analysis.restore_previous(a,'追記した資料です。',['追記した資料です。'])
        self.assertEqual(a._prev_lines,[])

    def _dirty_background(self):
        from analysis_context import Reads,signature
        a=self.a;owner=work.owner(a);lines=['冒頭','資料','資料','12+3','末尾']
        doc=a._input_document;doc.update('\n'.join(lines))
        doc.remember(3,5,'資料','しりょう');doc.remember(6,8,'資料','しりお')
        doc.remember_calculation(9,13,'12+3','15')
        results=[dict(original=line,corrected=line,_context_evidence=Reads({}).evidence(),
            _input_signature=signature((),doc.row_readings(i,line),doc.row_calculations(i,line)))
            for i,line in enumerate(lines)]
        base=dict(lines=lines,results=results,ctx={},dependencies=state_key(a))
        a._fg_parked={owner:base}
        doc.update('\n'.join(lines[1:]),edit=(0,3))
        state=dict(owner=owner,text=doc.text,lines=doc.text.split('\n'),ctx={},words={},attested={},
            dependencies=state_key(a),readings=doc.occurrences,calculations=doc.calculations)
        state.update(tab_analysis.background_values(a,doc.text,owner,None))
        return a,base,state

    def test_background_reuses_moved_rows_with_local_readings_and_calculation(self):
        a,base,state=self._dirty_background();tab_analysis.rebase_background(a,state)
        self.assertEqual(state['results'],base['results'][1:])
        self.assertNotIn('previous',state)

    def test_background_invalidates_changed_reading_and_removed_calculation_only(self):
        a,base,state=self._dirty_background();doc=a._input_document
        doc.remember(3,5,'資料','しりょう');doc.calculations=()
        state.update(readings=doc.occurrences,calculations=())
        tab_analysis.rebase_background(a,state)
        self.assertEqual(state['results'][0],base['results'][1])
        self.assertEqual(state['results'][1],base['results'][1])
        self.assertIsNone(state['results'][2])
        self.assertEqual(state['results'][3],base['results'][4])

    def test_background_rejects_unfinished_values_and_changed_context_proof(self):
        from analysis_context import Reads
        a,base,state=self._dirty_background()
        base['results'][1]['pending']=True;base['results'][2]['analysis_error']=True
        proof=Reads({'根拠':1});proof['根拠']
        base['results'][3]['_context_evidence']=proof.evidence();base['ctx']={'根拠':1}
        tab_analysis.rebase_background(a,state)
        self.assertEqual(state['results'][:3],[None,None,None])
        self.assertIsNotNone(state['results'][3])

if __name__=='__main__':unittest.main()