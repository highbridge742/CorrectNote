# -*- coding: utf-8 -*-
"""Process transport matches the application entry on isolated initial stores."""
import correction_entry
import time,unittest
from types import SimpleNamespace
from unittest.mock import Mock
import analysis_worker,analysis_async,analysis_work_app
from analysis_work import Document


def initial():
    from vocabulary import VocabularyStore
    from seed_vocabulary import load_seed
    from decisions import DecisionStore
    from last_choice import LastChoiceStore,set_active
    from ime_readings import IMEReadings
    from dict_index import DictIndex
    from context_vec import ContextVectorStore
    import kanji_guess
    store=VocabularyStore();load_seed(store)
    index=DictIndex();index.ensure_built()
    cv=ContextVectorStore();cv.ensure_seeded()
    choices=LastChoiceStore();choices.bind(store,index);set_active(choices)
    ime=IMEReadings();kanji_guess.set_ime_readings_provider(ime.readings_for)
    return SimpleNamespace(store=store,dict_index=index,choices=choices,decisions=DecisionStore(),
        ime_readings=ime,context_vec=cv,settings={'input_method':'kana'})


def wait(worker,identifier):
    end=time.monotonic()+90
    while time.monotonic()<end:
        value=worker.poll(identifier)
        if value is not None:return value
        time.sleep(.01)
    raise AssertionError('Worker timed out')


class EngineProcessTests(unittest.TestCase):

    def test_cacheless_inflections_match_entry_after_state_updates(self):
        import app
        a=initial();worker=analysis_worker.Worker()
        lines=['のひっています\t','意図をさして\t','残っています','遺っています']
        try:
            state=analysis_worker.snapshot(a)
            for line in lines:
                with self.subTest(line=line):
                    prepared=wait(worker,worker.submit(dict(kind='prepare',lines=[line]),state))
                    state=None
                    expected=app.correct_line(line,a.store,context_vocab=prepared['context'],
                        decisions=a.decisions,input_method='kana',context_vec=a.context_vec,
                        dict_index=a.dict_index)
                    actual=wait(worker,worker.submit(dict(kind='line',line=line,
                        context=prepared['context'],input_method='kana',attested=prepared['attested'])))
                    self.assertEqual(actual['result'],expected)
                    self.assertFalse(actual['result']['odd_spans'])
            a.decisions.protect('のひっています');a._analysis_state_revision=1
            request=dict(kind='line',line=lines[0],context={},input_method='kana',attested=())
            actual=wait(worker,worker.submit(request,analysis_worker.snapshot(a)))['result']
            self.assertEqual(actual['corrected'],lines[0])
            a.decisions=type(a.decisions)();a._analysis_state_revision=2
            actual=wait(worker,worker.submit(request,analysis_worker.snapshot(a)))['result']
            self.assertEqual(actual['corrected'],'残っています\t')
            self.assertFalse(actual['odd_spans'])
        finally:worker.close()
        self.assertFalse(worker.process.is_alive())

    def test_initial_results_and_decision_updates_match_original_entry(self):
        import app
        from vocabulary import build_context_vocab_cached
        a=initial();worker=analysis_worker.Worker()
        lines=['寒ぃ日だ。','よいでしょぅか。','今日も良い天気です。','書類を作成しました。',
               '作業が官僚しました。','もんじにゅうりょく','今日は😀晴れです。','']
        try:
            expected_context=build_context_vocab_cached(lines,a.store,{})
            prepared=wait(worker,worker.submit(dict(kind='prepare',lines=lines),analysis_worker.snapshot(a)))
            self.assertEqual(prepared['context'],expected_context)
            for line in lines:
                with self.subTest(line=line):
                    expected=app.correct_line(line,a.store,context_vocab=expected_context,decisions=a.decisions,
                        input_method='kana',context_vec=a.context_vec,dict_index=a.dict_index)
                    value=wait(worker,worker.submit(dict(kind='line',line=line,context=expected_context,
                        input_method='kana',attested=prepared['attested'])))
                    self.assertEqual(value['result'],expected)
            a.decisions.protect('寒ぃ')
            a._analysis_state_revision=1
            value=wait(worker,worker.submit(dict(kind='line',line=lines[0],context=expected_context,
                input_method='kana',attested=prepared['attested']),analysis_worker.snapshot(a)))
            expected=app.correct_line(lines[0],a.store,context_vocab=expected_context,decisions=a.decisions,
                input_method='kana',context_vec=a.context_vec,dict_index=a.dict_index)
            self.assertEqual(value['result'],expected)
            self.assertEqual(value['result']['corrected'],lines[0])
        finally:
            worker.close()
        self.assertFalse(worker.process.is_alive())

    def test_unit_rebuild_preserves_results_without_correction(self):
        from unittest.mock import patch
        import app
        a=initial();runtime=analysis_worker.Runtime();runtime.set_state(analysis_worker.snapshot(a))
        result=app.correct_line('寒ぃ日だ。',a.store,dict_index=a.dict_index,decisions=a.decisions)
        with patch.object(correction_entry,'correct_line',side_effect=AssertionError('Cache restore reran correction')):
            value=runtime.execute(dict(kind='units',result=result,lines=['寒ぃ日だ。']))
        self.assertIs(value['result'],result)
        self.assertTrue(value['corrected_units'][1])


class AsyncIdentityTests(unittest.TestCase):
    def test_old_a_b_a_result_is_never_applied(self):
        a=SimpleNamespace(settings={'input_method':'kana'},_work_epoch=1)
        work=analysis_work_app.token(a)
        a._analyze_work=work;a._analyze_dependencies=analysis_worker.state_key(a)
        a._analyze_todo=[0];a._analyze_pos=0;a._prev_lines=['元の文'];a.line_results=[{'original':'元の文'}]
        a._correction_worker=Mock();a._correction_worker.poll.return_value={'result':{'corrected':'古い答え'}}
        a._work_epoch+=2  # A→B→A, same string, different generation.
        analysis_async.line_step(a,1)
        self.assertEqual(a.line_results,[{'original':'元の文'}])
        a._correction_worker.poll.assert_not_called()

    def test_changed_dependencies_restart_plan(self):
        a=SimpleNamespace(settings={'input_method':'kana'},_work_epoch=1,_analyze=Mock())
        a._analyze_work=analysis_work_app.token(a);a._analyze_dependencies=analysis_worker.state_key(a)
        a._analysis_state_revision=1
        analysis_async.line_step(a,1)
        a._analyze.assert_called_once()


    def _foreground(self):
        a=SimpleNamespace(settings={'input_method':'kana'},_work_epoch=1,
            root=Mock(),status=Mock(),_analyze=Mock())
        a._analyze_work=analysis_work_app.token(a)
        a._analyze_dependencies=analysis_worker.state_key(a)
        a._analyze_todo=[0,1];a._analyze_pos=1
        a._prev_lines=['完成した行','未処理の行'];a._analyze_text='\n'.join(a._prev_lines)
        a.line_results=[dict(original='完成した行',corrected='完成した行'),
                        dict(original='未処理の行',corrected='未処理の行',pending=True)]
        a._blank_result=lambda text:dict(original=text,corrected=text,pending=True)
        a._analyze_ctx={};a._nearby_words_for=lambda i:()
        return a

    def test_prepare_process_exit_restarts_once_for_the_current_input(self):
        from unittest.mock import patch
        a=self._foreground()
        with patch.object(analysis_async,'_request'), \
                patch.object(analysis_async,'_poll',side_effect=analysis_worker.WorkerExitedError('exit')), \
                patch.object(analysis_async,'_error') as report:
            for attempt in range(2):
                analysis_async.context(a,a._analyze_text,a._prev_lines)
                a.root.after.call_args[0][1]()
            a._analyze.assert_called_once()
            report.assert_called_once()
            self.assertIsNone(a._async_context_scope)

    def test_line_process_exit_retries_same_row_and_keeps_finished_rows(self):
        from unittest.mock import patch
        a=self._foreground();first=a.line_results[0]
        with patch.object(analysis_async,'_poll',side_effect=analysis_worker.WorkerExitedError('exit')), \
                patch.object(analysis_async,'_error') as report:
            analysis_async.line_step(a,1)
            self.assertEqual(a._analyze_pos,1)
            self.assertTrue(a.line_results[1]['pending'])
            self.assertIs(a.line_results[0],first)
            report.assert_not_called()
        with patch.object(analysis_async,'_poll',return_value=(False,None)), \
                patch.object(analysis_async,'_request') as request:
            analysis_async.line_step(a,1)
            self.assertEqual(request.call_args[0][1]['line'],'未処理の行')
            self.assertEqual(a._analyze_pos,1)

    def test_repeated_process_exit_reports_failure_instead_of_retry_loop(self):
        from unittest.mock import patch
        a=self._foreground()
        with patch.object(analysis_async,'_poll',side_effect=analysis_worker.WorkerExitedError('exit')), \
                patch.object(analysis_async,'_error') as report:
            analysis_async.line_step(a,1);analysis_async.line_step(a,1)
            self.assertEqual(a._analyze_pos,2)
            self.assertTrue(a.line_results[1]['analysis_error'])
            report.assert_called_once()

    def test_ordinary_engine_error_is_not_retried(self):
        from unittest.mock import patch
        a=self._foreground()
        with patch.object(analysis_async,'_poll',side_effect=RuntimeError('engine error')), \
                patch.object(analysis_async,'_error') as report:
            analysis_async.line_step(a,1)
            self.assertEqual(a._analyze_pos,2)
            self.assertTrue(a.line_results[1]['analysis_error'])
            self.assertFalse(hasattr(a,'_foreground_worker_retry'))
            report.assert_called_once()

    def test_retry_budget_is_shared_by_phases_and_reset_by_new_input(self):
        a=self._foreground();error=analysis_worker.WorkerExitedError('exit')
        self.assertTrue(analysis_async._retry_foreground_exit(a,error))
        self.assertFalse(analysis_async._retry_foreground_exit(a,error))
        a._work_epoch+=1
        self.assertTrue(analysis_async._retry_foreground_exit(a,error))



class QuickServeCancellationTests(unittest.TestCase):
    def serve(self,kind,body):
        import queue
        import analysis_context as C
        from unittest.mock import patch
        inbox=queue.Queue();inbox.put(dict(id=1,task={'kind':kind,'label':'old'},state='A'))
        states=[];outputs=[];events=[]
        class Runtime:
            state=None
            def set_state(self,state):self.state=state;states.append(state)
            def execute(self,task):return body(self,task,inbox,events)
        class Outbox:
            def put(self,value):
                outputs.append(value)
                if value[0] in (2,3) or value[2]:inbox.put(None)
        with patch.object(analysis_worker,'Runtime',Runtime):analysis_worker._serve(inbox,Outbox())
        self.assertIsNone(C._REQUEST_CHECK.get());return states,outputs,events

    def test_preempted_quick_keeps_state_from_intermediate_request_for_latest(self):
        import analysis_context as C
        import ime_session as P
        closed=[]
        class Resource:
            def close(self):closed.append(True)
        def body(runtime,task,inbox,events):
            if task['label']=='old':
                inbox.put(dict(id=2,task={'kind':'quick','label':'intermediate'},state='B'))
                inbox.put(dict(id=3,task={'kind':'quick','label':'latest'},state=None))
                with P.resource_scope():
                    P.retain(Resource());C.check_current_request()
                self.fail('old quick continued')
            self.assertEqual(task['label'],'latest');self.assertEqual(closed,[True]);C.check_current_request()
            return {'label':task['label'],'state':runtime.state}
        states,outputs,events=self.serve('quick',body)
        self.assertEqual(states,['A','B']);self.assertEqual(outputs,[(3,{'label':'latest','state':'B'},None)])
        self.assertIsNone(P._CURRENT.get())

    def test_close_request_unwinds_inflight_quick_without_partial_output(self):
        import analysis_context as C
        def body(runtime,task,inbox,events):
            inbox.put(None)
            try:C.check_current_request()
            finally:events.append('unwound')
        states,outputs,events=self.serve('quick',body)
        self.assertEqual(states,['A']);self.assertEqual(outputs,[]);self.assertEqual(events,['unwound'])

    def test_main_tasks_yield_to_new_input_without_publishing_old_results(self):
        import analysis_context as C
        import ime_session as P
        for kind in ('line','units','prepare'):
            with self.subTest(kind=kind):
                closed=[]
                class Resource:
                    def close(self):closed.append(True)
                def body(runtime,task,inbox,events):
                    if task['label']=='old':
                        inbox.put(dict(id=2,task={'kind':'prepare','label':'latest'},state='B'))
                        with P.resource_scope():
                            P.retain(Resource());C.check_current_request()
                        self.fail('obsolete main analysis continued')
                    self.assertEqual(closed,[True])
                    return task['label']
                states,outputs,events=self.serve(kind,body)
                self.assertEqual(states,['A','B'])
                self.assertEqual(outputs,[(2,'latest',None)])
                self.assertIsNone(P._CURRENT.get())

    def test_main_completed_but_obsolete_result_is_not_emitted(self):
        for kind in ('line','units','prepare'):
            with self.subTest(kind=kind):
                def body(runtime,task,inbox,events):
                    if task['label']=='old':inbox.put(dict(id=2,task={'kind':kind,'label':'latest'},state='B'))
                    return task['label']
                states,outputs,events=self.serve(kind,body)
                self.assertEqual(outputs,[(2,'latest',None)])

    def test_request_arriving_after_result_preparation_is_preserved_before_emission(self):
        def body(runtime,task,inbox,events):
            if task['label']=='old':inbox.put(dict(id=2,task={'kind':'quick','label':'latest'},state='B'))
            return task['label']
        states,outputs,events=self.serve('quick',body)
        self.assertEqual(states,['A','B']);self.assertEqual(outputs,[(2,'latest',None)])

    def test_real_engine_error_is_reported_and_scope_is_restored(self):
        def body(runtime,task,inbox,events):raise ValueError('body failure')
        states,outputs,events=self.serve('quick',body)
        self.assertEqual(states,['A']);self.assertEqual(len(outputs),1);self.assertEqual(outputs[0][:2],(1,None))
        self.assertIn('ValueError: body failure',outputs[0][2])

if __name__=='__main__':unittest.main()