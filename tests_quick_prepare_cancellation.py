"""Required quick resources yield only at completed boundaries, preserving state."""
import copy,queue,unittest
from contextlib import ExitStack
from unittest.mock import patch
import analysis_context as A
import analysis_worker as W
import familiar_nominal as F
import corrector as C
import oddness as O


class EndingInbox(queue.Queue):
    """Empty blocking reads are controlled EOF; nonblocking reads keep Empty."""
    def get(self,block=True,timeout=None):
        try:return super().get(block=False)
        except queue.Empty:
            if not block:raise
            return None


class QuickPrepareCancellationTests(unittest.TestCase):
    def loads(self,stack,calls,after=None):
        def run(name):
            def invoke(*args):
                calls.append((name,args))
                if after:after(name)
                return ()
            return invoke
        stack.enter_context(patch.object(F,'families',run('families')))
        stack.enter_context(patch.object(C,'_table_readings_for_surface',run('table')))
        stack.enter_context(patch.object(O,'_load',run('oddness')))

    def test_current_preparation_keeps_required_resources_none_and_outer_scope(self):
        import contextual_repair as Q,ngram_yomi as N
        expected=[('families',()),('table',('',)),('oddness',())]
        for scoped in (False,True):
            with self.subTest(scoped=scoped),ExitStack() as stack:
                calls=[];runtime=W.Runtime();before=copy.deepcopy(vars(runtime))
                self.loads(stack,calls)
                for obj,name in ((Q,'_native_written_nominal_readings'),(Q,'_seed_context'),(N,'_bigram_counts')):
                    stack.enter_context(patch.object(obj,name,side_effect=AssertionError('optional resource requested')))
                if scoped:stack.enter_context(A.request_scope(lambda:False))
                outer=A._REQUEST_CHECK.get()
                self.assertIsNone(runtime.execute({'kind':'quick_prepare'}))
                self.assertEqual(calls,expected);self.assertEqual(vars(runtime),before)
                self.assertIs(A._REQUEST_CHECK.get(),outer)
        self.assertIsNone(A._REQUEST_CHECK.get())

    def test_already_obsolete_preparation_loads_no_resource(self):
        calls=[]
        with ExitStack() as stack:
            self.loads(stack,calls)
            with A.request_scope(lambda:True),self.assertRaises(A.SupersededAnalysis):
                W.Runtime().execute({'kind':'quick_prepare'})
        self.assertEqual(calls,[]);self.assertIsNone(A._REQUEST_CHECK.get())

    def test_cancel_and_close_at_each_completed_boundary_publish_nothing(self):
        expected=[('families',()),('table',('',)),('oddness',())]
        for boundary in range(1,4):
            for following in ('cancel','close'):
                with self.subTest(boundary=boundary,following=following),ExitStack() as stack:
                    calls=[];inbox=EndingInbox();outbox=queue.Queue()
                    inbox.put(dict(id=1,task={'kind':'quick_prepare'},state=None))
                    def arrival(name):
                        if len(calls)==boundary:
                            inbox.put(None if following=='close' else dict(id=2,task={'kind':'cancel'},state=None))
                    self.loads(stack,calls,arrival)
                    with A.request_scope(lambda:False):
                        outer=A._REQUEST_CHECK.get();W._serve(inbox,outbox)
                        self.assertIs(A._REQUEST_CHECK.get(),outer)
                    self.assertEqual(calls,expected[:boundary]);self.assertTrue(outbox.empty())
        self.assertIsNone(A._REQUEST_CHECK.get())

    def test_next_real_quick_receives_intervening_state_without_old_output(self):
        from tests_analysis_async import initial
        from last_choice import set_active,LastChoiceStore
        from vocabulary import VocabularyStore
        from ime_readings import IMEReadings
        from decisions import DecisionStore
        from context_vec import ContextVectorStore
        import charngram,ime_session,morphology
        state=initial();a=W.snapshot(state)
        state.ime_readings._pairs={'資料':['しりょう']};b=W.snapshot(state)
        task=dict(kind='quick',lines=['資料を保存しました。'],input_method='kana',calculations={})
        def model(runtime):
            return copy.deepcopy((runtime.store.to_list(),runtime.store.revision(),runtime.ime._pairs,
                runtime.choices._readings,runtime.choices._units,runtime.choices.revision(),
                runtime.decisions._rejected,runtime.decisions._protected,runtime.decisions._odd_only,
                runtime.context_vec._co,charngram._LEARNED))
        try:
            with ExitStack() as stack:
                for cls in (VocabularyStore,LastChoiceStore,IMEReadings,DecisionStore,ContextVectorStore):
                    stack.enter_context(patch.object(cls,'save',side_effect=AssertionError('No saves')))
                stack.enter_context(patch.object(LastChoiceStore,'record',side_effect=AssertionError('No choice learning')))
                stack.enter_context(patch.object(IMEReadings,'remember',side_effect=AssertionError('No input retention')))
                stack.enter_context(patch.object(charngram,'learn',side_effect=AssertionError('No text learning')))
                stack.enter_context(patch.object(charngram,'save',side_effect=AssertionError('No text saving')))
                expected_runtime=W.Runtime();expected_runtime.set_state(b)
                expected=expected_runtime.execute(task);expected_model=model(expected_runtime)
                runtime=W.Runtime();inbox=EndingInbox();outbox=queue.Queue();states=[];loads=[];executed=[]
                inbox.put(dict(id=1,task={'kind':'quick_prepare'},state=a))
                original_state=runtime.set_state;original_quick=runtime.quick;original_family=F.families
                def set_state(value):states.append(value);return original_state(value)
                def families():
                    result=original_family();loads.append('families')
                    if len(loads)==1:
                        inbox.put(dict(id=2,task={'kind':'quick_prepare'},state=b))
                        inbox.put(dict(id=3,task=task,state=None))
                    return result
                def quick(value):
                    executed.append(value)
                    self.assertEqual(states,[a,b]);self.assertEqual(loads,['families'])
                    self.assertEqual(runtime.ime._pairs,b['ime'])
                    self.assertIsNone(morphology._TOKENIZATION_CACHE.get())
                    self.assertIsNone(ime_session._CURRENT.get())
                    return original_quick(value)
                stack.enter_context(patch.object(runtime,'set_state',set_state))
                stack.enter_context(patch.object(runtime,'quick',quick))
                stack.enter_context(patch.object(F,'families',families))
                # Old preparation must not reach its next table, while real quick
                # still uses ordinary table/oddness calls if it needs them.
                table=C._table_readings_for_surface;words=O._load
                def check_table(*args):
                    self.assertTrue(executed,'obsolete preparation reached table')
                    return table(*args)
                def check_words(*args):
                    self.assertTrue(executed,'obsolete preparation reached oddness')
                    return words(*args)
                stack.enter_context(patch.object(C,'_table_readings_for_surface',check_table))
                stack.enter_context(patch.object(O,'_load',check_words))
                stack.enter_context(patch.object(W,'Runtime',return_value=runtime))
                with A.request_scope(lambda:False):
                    outer=A._REQUEST_CHECK.get();W._serve(inbox,outbox)
                    self.assertIs(A._REQUEST_CHECK.get(),outer)
                outputs=[]
                while not outbox.empty():outputs.append(outbox.get_nowait())
                self.assertEqual(outputs,[(3,expected,None)])
                self.assertEqual(executed,[task]);self.assertEqual(model(runtime),expected_model)
                self.assertIsNone(A._REQUEST_CHECK.get())
                self.assertIsNone(morphology._TOKENIZATION_CACHE.get());self.assertIsNone(ime_session._CURRENT.get())
        finally:set_active(None)

    def test_real_resource_failure_is_reported_and_scope_is_restored(self):
        inbox=EndingInbox();outbox=queue.Queue()
        inbox.put(dict(id=1,task={'kind':'quick_prepare'},state=None))
        with patch.object(F,'families',side_effect=ValueError('synthetic resource failure')),\
             patch.object(C,'_table_readings_for_surface') as table,patch.object(O,'_load') as words:
            W._serve(inbox,outbox)
        identifier,value,error=outbox.get_nowait()
        self.assertEqual((identifier,value),(1,None));self.assertIn('ValueError: synthetic resource failure',error)
        self.assertTrue(outbox.empty());table.assert_not_called();words.assert_not_called()
        self.assertIsNone(A._REQUEST_CHECK.get())


if __name__=='__main__':unittest.main()
