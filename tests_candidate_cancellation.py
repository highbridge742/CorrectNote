# -*- coding: utf-8 -*-
"""A newer input request interrupts candidate validation before lexical work."""
import queue
import unittest
from contextlib import ExitStack
from contextvars import copy_context
from copy import deepcopy
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
import analysis_context as A
import analysis_worker as W
import contextual_repair as Q
import ime_session as I
import morphology as M


class CandidateCancellationTests(unittest.TestCase):
    def test_superseded_candidate_stops_before_reading_the_target_or_gate(self):
        class UnreadTarget:
            @property
            def text(self):
                raise AssertionError('obsolete target was inspected')
        with A.request_scope(lambda:True):
            with self.assertRaises(A.SupersededAnalysis):
                Q.validate(UnreadTarget(),'候補',None,None,None,None)
        self.assertIsNone(A._REQUEST_CHECK.get())

    def test_unscoped_and_current_request_keep_unchanged_reason(self):
        target=SimpleNamespace(text='資料')
        self.assertEqual(Q.validate(target,'資料',None,None,None,None),(False,'unchanged'))
        checks=[]
        def current():checks.append(True);return False
        with A.request_scope(current):
            self.assertEqual(Q.validate(target,'資料',None,None,None,None),(False,'unchanged'))
        self.assertEqual(checks,[True])
        self.assertIsNone(A._REQUEST_CHECK.get())

    def test_copied_request_context_does_not_cancel_another_thread(self):
        values=[];errors=[];checks=[]
        def stale():checks.append(True);return True
        def work():
            try:values.append(Q.validate(SimpleNamespace(text='資料'),'資料',None,None,None,None))
            except BaseException as error:errors.append(error)
        with A.request_scope(stale):
            context=copy_context();thread=Thread(target=context.run,args=(work,))
            thread.start();thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(values,[(False,'unchanged')]);self.assertEqual(errors,[])
        self.assertEqual(checks,[]);self.assertIsNone(A._REQUEST_CHECK.get())

    def test_worker_keeps_latest_state_and_emits_no_obsolete_or_partial_row(self):
        # Same-priority requests must supersede too. Resource release precedes
        # the latest result, and an intervening state update is retained.
        for kind in ('line','quick'):
            with self.subTest(kind=kind):
                inbox=queue.Queue();outbox=queue.Queue();states=[];closed=[];executed=[]
                inbox.put(dict(id=1,task={'kind':kind,'line':'古い行'},state='A'))
                owner=self
                class Handle:
                    def close(self):closed.append(True)
                class Runtime:
                    state=None
                    def set_state(self,state):self.state=state;states.append(state)
                    def execute(self,task):
                        executed.append(task['line'])
                        if task['line']=='古い行':
                            inbox.put(dict(id=2,task={'kind':kind,'line':'途中の行'},state='B'))
                            inbox.put(dict(id=3,task={'kind':kind,'line':'資料'},state=None))
                            with M.tokenization_scope(),I.resource_scope():
                                I.retain(Handle())
                                Q.validate(SimpleNamespace(text='古い行'),'候補',None,None,None,None)
                            owner.fail('obsolete validation returned')
                        owner.assertEqual(closed,[True]);owner.assertEqual(self.state,'B')
                        owner.assertIsNone(M._TOKENIZATION_CACHE.get());owner.assertIsNone(I._CURRENT.get())
                        owner.assertEqual(Q.validate(SimpleNamespace(text='資料'),'資料',None,None,None,None),(False,'unchanged'))
                        return dict(original=task['line'],corrected=task['line'],analysis_status='complete')
                class Outbox:
                    def put(self,value):outbox.put(value);inbox.put(None)
                with patch.object(W,'Runtime',Runtime):W._serve(inbox,Outbox())
                self.assertEqual(states,['A','B']);self.assertEqual(executed,['古い行','資料'])
                self.assertEqual(outbox.get_nowait(),(3,dict(original='資料',corrected='資料',analysis_status='complete'),None))
                self.assertTrue(outbox.empty());self.assertIsNone(A._REQUEST_CHECK.get())

    def test_stop_and_cancel_unwind_validation_without_publishing_a_result(self):
        for following in ('stop','cancel'):
            with self.subTest(following=following):
                inbox=queue.Queue();outputs=[];unwound=[];states=[];owner=self
                inbox.put(dict(id=1,task={'kind':'line'},state='A'))
                class Runtime:
                    def set_state(self,state):
                        states.append(state)
                        if state=='B':inbox.put(None)
                    def execute(self,task):
                        if following=='stop':inbox.put(None)
                        else:inbox.put(dict(id=2,task={'kind':'cancel'},state='B'))
                        try:Q.validate(SimpleNamespace(text='古い行'),'候補',None,None,None,None)
                        finally:unwound.append(True)
                        owner.fail('obsolete validation returned')
                class Outbox:
                    def put(self,value):outputs.append(value);inbox.put(None)
                with patch.object(W,'Runtime',Runtime):W._serve(inbox,Outbox())
                self.assertEqual(outputs,[]);self.assertEqual(unwound,[True])
                self.assertEqual(states,['A'] if following=='stop' else ['A','B'])
                self.assertIsNone(A._REQUEST_CHECK.get())

    def test_actual_correction_unwinds_without_learning_and_latest_coordinates_match(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        import charngram,corrector,ime_inverse_gate,units
        state=initial();runtime=W.Runtime();runtime.set_state(W.snapshot(state));runtime.prepare_tables()
        old='処理がじゃのになっていないだろうか\t';latest='資料を保存しました。'
        old_context=runtime.execute(dict(kind='prepare',lines=[old]))
        current=runtime.execute(dict(kind='prepare',lines=[latest]))
        task=dict(kind='line',line=latest,input_method='kana',context=current['context'],attested=current['attested'])
        def model():
            return deepcopy((runtime.store.to_list(),runtime.store.revision(),
                runtime.choices._readings,runtime.choices._units,runtime.choices.revision(),
                runtime.ime._pairs,runtime.decisions._protected,runtime.decisions._rejected,
                runtime.decisions._odd_only,charngram._LEARNED,runtime.context_vec._co))
        original=Q.validate;obsolete=False;entered=[]
        def arrival(target,surface,*args,**kwargs):
            nonlocal obsolete
            obsolete=True;entered.append(surface)
            return original(target,surface,*args,**kwargs)
        try:
            with ExitStack() as guards:
                for store in (runtime.store,runtime.choices,runtime.ime,runtime.decisions,runtime.context_vec):
                    guards.enter_context(patch.object(store,'save',side_effect=AssertionError('analysis tried to save')))
                guards.enter_context(patch.object(runtime.choices,'record',side_effect=AssertionError('analysis tried to learn a choice')))
                guards.enter_context(patch.object(runtime.ime,'remember',side_effect=AssertionError('analysis tried to retain input')))
                guards.enter_context(patch.object(charngram,'learn',side_effect=AssertionError('analysis tried to learn text')))
                guards.enter_context(patch.object(charngram,'save',side_effect=AssertionError('analysis tried to save text')))
                expected=runtime.execute(task);before=model()
                with patch.object(Q,'validate',arrival),patch.object(units,'build_line_units') as display,patch.object(units,'build_suspect_units') as suspect:
                    with A.request_scope(lambda:obsolete),self.assertRaises(A.SupersededAnalysis):
                        runtime.execute(dict(kind='line',line=old,input_method='kana',context=old_context['context'],attested=old_context['attested']))
                    self.assertEqual(len(entered),1);display.assert_not_called();suspect.assert_not_called()
                self.assertEqual(model(),before)
                for value in (Q._SEARCH.get(),corrector._CORRECTION_SOURCE.get(),
                              ime_inverse_gate._CORRECTION_CACHE.get(),M._TOKENIZATION_CACHE.get(),
                              I._CURRENT.get(),A._REQUEST_CHECK.get(),runtime._ime_queries):
                    self.assertIsNone(value)
                self.assertEqual(corrector._CORRECTION_PATH.get(),())
                with A.request_scope(lambda:False):actual=runtime.execute(task)
                self.assertEqual(actual,expected);self.assertEqual(model(),before)
                self.assertEqual(actual['result']['original'],latest)
                self.assertEqual(actual['result']['analysis_status'],'complete')
                for key in ('original_units','corrected_units'):
                    text,rows=actual[key];self.assertEqual(text,latest)
                    for row in rows:self.assertEqual(text[row['start']:row['end']],row['text'])
        finally:set_active(None)


if __name__=='__main__':unittest.main()
