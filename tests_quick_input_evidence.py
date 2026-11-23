# -*- coding: utf-8 -*-
"""Quick widget owns brackets and positioned readings independently of main."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import tkinter as tk
import app,ime_watch,analysis_work_app as work
from analysis_work import observe_text,Occurrence,occurrence_readings
from ime_commit_ranges import CommitRanges
import tests_bracket_composition as bracket_tests
import tests_quick_async as quick_tests


class QuickEvidenceTests(unittest.TestCase):
    setUp=quick_tests.QuickAsyncTests.setUp
    def test_readings_are_row_local_and_new_reading_resubmits(self):
        import quick_analysis as Q
        self.widget.text='橋を渡る\n橋を見る'
        doc=work.quick_document(self.app,self.widget.text)
        doc.remember(5,6,'橋','ばし')
        Q.start(self.app)
        task=self.worker.submit.call_args[0][0]
        self.assertEqual(task['readings'],{0:(),1:(Occurrence(0,1,'橋','ばし'),)})
        doc.remember(0,1,'橋','はし');Q.start(self.app)
        self.assertEqual(self.worker.submit.call_count,2)
        self.assertEqual(self.worker.submit.call_args[0][0]['readings'][0][0].reading,'はし')

    def test_worker_enters_exact_line_reading_scope_and_clears_it(self):
        from analysis_worker import Runtime
        r=Runtime.__new__(Runtime)
        # 簡易入力の答えは境目の案内（collect_navigation・text_navigation.plans）も集めるようになり、tokenize の答えを
        # 並べる。作り物の tokenize は空の並びを返す（Mock のままでは並べられず落ちた・試験が古い・2026-11-20）
        r.store=Mock();r.tokenize=Mock(return_value=());r.decisions=None;r.context_vec=None;r.index=None;r.choices=None
        seen=[]
        def correct(line,*args,**kwargs):
            seen.append((line,occurrence_readings(line,0,1),occurrence_readings(line,2,3)))
            return dict(original=line,corrected=line)
        task=dict(lines=['橋と橋','橋と橋'],input_method='kana',calculations={},
                  readings={0:(Occurrence(2,3,'橋','ばし'),),1:(Occurrence(0,1,'橋','はし'),)})
        with patch('corrector.correct_line',side_effect=correct),patch('quote_calculator.apply_to_result',side_effect=lambda result,*a:result),patch('units.build_suspect_units',return_value=('',[])),patch('units.build_line_units',return_value=('',[])):
            r.quick(task)
        self.assertEqual(seen,[('橋と橋',(),('ばし',)),('橋と橋',('はし',),())])
        self.assertEqual(occurrence_readings('橋と橋',0,1),())


class QuickWidgetTests(unittest.TestCase):
    setUp=bracket_tests.BracketCompositionTests.setUp
    tearDown=bracket_tests.BracketCompositionTests.tearDown
    wait=bracket_tests.BracketCompositionTests.wait
    def quick(self):
        w=tk.Text(self.root,undo=True);w.pack();self.a._quick_text=w
        self.a._on_quick_change=Mock()
        work.quick_document(self.a,'')
        observe_text(w,lambda text,discard,edit:work.quick_edited(self.a,text,discard,edit))
        return w
    def press(self,w,state=0):
        self.a._on_f5_brackets(SimpleNamespace(widget=w,keysym='F2',char='',state=state))
    def test_quick_cycles_selection_modifiers_and_undo_without_editing_main(self):
        w=self.quick()
        with patch.object(ime_watch,'composition_active',return_value=False):
            for state,first in ((0,'（語）'),(1,'『語』'),(4,'（語）'),(5,'“語”'),(0x20000,'語（）')):
                w.delete('1.0','end');w.insert('1.0','語');w.tag_add('sel','1.0','end-1c')
                self.a._forget_bracket_cycle();self.press(w,state)
                self.assertEqual(w.get('1.0','end-1c'),first)
                self.press(w,state);self.assertNotEqual(w.get('1.0','end-1c'),first)
                self.assertTrue(self.a._cancel_bracket_cycle(w));self.assertEqual(w.get('1.0','end-1c'),'語')
                self.assertEqual(self.editor.get('1.0','end-1c'),'前後')
            w.delete('1.0','end');w.insert('1.0','abc');w.tag_add('sel','1.0','end-1c')
            self.a._forget_bracket_cycle();self.press(w)
            self.assertEqual(w.get('1.0','end-1c'),'(abc)')
            w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'abc')
    def test_quick_f2_and_delayed_commit_preserve_reading_and_owner(self):
        w=self.quick();w.insert('1.0','先橋末');w.mark_set('insert','1.0')
        self.a._f2_focus_target=dict(widget=w,row=1,start=1,end=2,text='橋')
        with patch.object(ime_watch,'composition_active',return_value=False):self.press(w)
        self.assertEqual(w.get('1.0','end-1c'),'先（橋）末')
        self.a._f2_focus_target=None;self.a._forget_bracket_cycle()
        w.delete('1.0','end');w.insert('1.0','前後');w.mark_set('insert','1.1');active=[True]
        ranges=CommitRanges();ranges.set_owner(w)
        events=SimpleNamespace(ranges=ranges,complete_current=lambda text:(True,(('橋','はし'),)))
        self.a._quick_ime_result_events=events
        def commit(text):
            self.root.after(20,lambda:(w.insert('insert','橋'),active.__setitem__(0,False)))
            return True,(('橋','はし'),)
        events.complete_current=commit
        with patch.object(ime_watch,'composition_active',side_effect=lambda hwnd:active[0]),patch.object(ime_watch,'read_composition',return_value={'comp':'橋','comp_reading':'はし'}),patch.object(work,'drain_quick_readings'):
            self.press(w);self.press(w)
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(w.get('1.0','end-1c'),'前「橋」後')
        self.assertEqual(work.quick_document(self.a,w.get('1.0','end-1c')).occurrences,(Occurrence(2,3,'橋','はし'),))
        self.assertEqual(self.editor.get('1.0','end-1c'),'前後')
    def test_closed_quick_pending_commit_cannot_wrap_reopened_widget(self):
        w=self.quick();w.insert('1.0','前後');w.mark_set('insert','1.1')
        with patch.object(ime_watch,'composition_active',return_value=True),patch.object(ime_watch,'read_composition',return_value={'comp':'橋'}),patch.object(ime_watch,'complete_composition',return_value=True):
            self.press(w)
        pending=self.a._pending_bracket_composition
        self.a._discard_widget_brackets(w);w.destroy();new=self.quick();new.insert('1.0','前橋後')
        self.a._finish_bracket_composition(pending)
        self.assertEqual(new.get('1.0','end-1c'),'前橋後')
        self.assertEqual(self.editor.get('1.0','end-1c'),'前後')
    def test_commit_ranges_bind_only_actual_new_occurrence_and_clear_on_undo(self):
        w=self.quick();w.insert('1.0','橋と');w.edit_separator()
        ranges=CommitRanges();ranges.set_owner(w)
        self.a._quick_ime_result_events=SimpleNamespace(ranges=ranges,take=lambda:())
        ranges.begin();ranges.result('橋','ばし');w.insert('end-1c','橋');ranges.finish()
        self.assertTrue(work.drain_quick_readings(self.a))
        self.assertEqual(work.quick_document(self.a,'橋と橋').occurrences,(Occurrence(2,3,'橋','ばし'),))
        w.edit_undo()
        self.assertFalse(work.quick_document(self.a,w.get('1.0','end-1c')).occurrences)

    def test_escape_removes_quick_brackets_then_closes_on_next_press(self):
        w=self.quick();w.insert('1.0','語');w.tag_add('sel','1.0','end-1c')
        self.a._close_quick_capture=Mock()
        with patch.object(ime_watch,'composition_active',return_value=False):self.press(w)
        self.assertEqual(self.a._on_quick_escape(),'break')
        self.assertEqual(w.get('1.0','end-1c'),'語');self.a._close_quick_capture.assert_not_called()
        self.a._on_quick_escape();self.a._close_quick_capture.assert_called_once()

