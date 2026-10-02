# -*- coding: utf-8 -*-
"""Saved corrections still need their display prepared before opening a tab."""
import unittest
from unittest.mock import Mock,patch
import tests_background_ownership
import analysis_async,analysis_work_app as work,tab_analysis


class BackgroundDisplayTests(unittest.TestCase):
    def setUp(self):
        original=tests_background_ownership.BackgroundOwnershipTests();original.setUp();self.a=original.a
        self.a._input_documents.clear()
        self.a._prune_analysis_cache=Mock()
        self.a._prev_active=None
        self.text=self.a.session.tabs[1]['text']
        self.owner=work.owner_for_tab(self.a,self.a.session.tabs[1])
        self.results=[dict(original=line,corrected=line) for line in self.text.split('\n')]
        self.a._analysis_cache[self.text]=self.results
        self.a._analysis_cache_dependencies[self.text]=analysis_async.state_key(self.a)

    def start(self):
        self.a._start_background_tabs()
        self.assertTrue(self.a._bg_texts,'Text-only results skipped their display prefetch')
        self.assertTrue(self.a._bg_step_once())
        return self.a._bg

    def test_next_tab_is_prepared_before_a_large_previous_tab(self):
        a=self.a;a._prev_active=2
        a.session.tabs[2]['text']='旧資料を確認します。\n'*2065
        a._start_background_tabs()
        owners=[owner for owner,text in a._bg_texts]
        self.assertEqual(owners[0],work.owner_for_tab(a,a.session.tabs[1]))
        self.assertEqual(owners[1],work.owner_for_tab(a,a.session.tabs[2]))

    def test_text_cache_submits_only_display_work(self):
        a=self.a;state=self.start();requests=[]
        prepared=dict(context={},words={},attested={})
        def request(app,task,scope,background=False):requests.append((task,background))
        with patch.object(analysis_async,'cached_context',return_value=prepared), \
                patch.object(analysis_async,'_poll',return_value=(False,None)), \
                patch.object(analysis_async,'_request',side_effect=request):
            analysis_async.background_step(a,state)
            analysis_async.background_step(a,state)
        self.assertEqual([task['kind'] for task, _ in requests],['units'])
        self.assertTrue(all(background for _, background in requests))
        self.assertIs(requests[0][0]['result'],self.results[0])

    def test_owner_values_without_display_are_prefetched(self):
        a=self.a
        tab_analysis._save(a,self.owner,self.text,self.results,
            dict(context={},words={},attested={}),{},{},analysis_async.state_key(a),())
        state=self.start()
        self.assertEqual(state['results'],self.results)

    def test_partial_display_is_preserved_after_editing_another_tab(self):
        a=self.a;state=self.start()
        first=self.results[0];key=(first['original'],first['corrected'])
        state.update(ctx={},words={},attested={},units={key:(first['corrected'],[])},
            suspect_units={key+(False,):(first['original'],[])},pos=1)
        a._work_epoch+=1
        with patch.object(analysis_async,'background_step') as step:
            a._bg_step_once();step.assert_called_once_with(a,state)
        self.assertIs(a._bg,state)
        self.assertEqual(state['pos'],1,'Unprepared display rows were treated as finished')
        a._stop_background_tabs()
        self.assertEqual(a._bg_parked[self.owner]['units'],state['units'])

    def test_prepared_owner_does_not_submit_again(self):
        a=self.a
        units={(r['original'],r['corrected']):(r['corrected'],[]) for r in self.results}
        suspect={(r['original'],r['corrected'],False):(r['original'],[]) for r in self.results}
        tab_analysis._save(a,self.owner,self.text,self.results,
            dict(context={},words={},attested={}),units,suspect,analysis_async.state_key(a),())
        # Use a distinct second tab so its own missing preparation cannot alias.
        a.session.tabs[2]['text']='別の文'
        a._start_background_tabs()
        self.assertNotIn((self.owner,self.text),a._bg_texts)


    def test_display_rebuild_uses_calculation_owner_not_shared_text(self):
        from analysis_work import Document
        a=self.a;text='40';a.session.tabs[1]['text']=text
        doc=Document(self.owner,text);doc.remember_calculation(0,2,text,text)
        a._input_documents[self.owner]=doc
        results=[dict(original=text,corrected=text,details=[(text,text,'計算')])]
        tab_analysis._save(a,self.owner,text,results,
            dict(context={},words={},attested={}),{},{},analysis_async.state_key(a),(),doc.calculations)
        a._analysis_cache[text]=[dict(original=text,corrected='四十')]
        a._analysis_cache_dependencies[text]=analysis_async.state_key(a)
        a._tab_units_cache={text:({(text,text):('四十',[])},{})}
        state=self.start()
        self.assertEqual(state['results'],results)
        self.assertEqual(state['calculations'],doc.calculations)
        self.assertEqual(state['units'],{})
        requests=[]
        with patch.object(analysis_async,'_poll',return_value=(False,None)), \
                patch.object(analysis_async,'_request',side_effect=lambda app,task,scope,background=False:requests.append((task,background))):
            analysis_async.background_step(a,state)
        self.assertEqual(requests[0][0]['kind'],'units')
        self.assertTrue(requests[0][1])
        self.assertEqual(requests[0][0]['result'],results[0])



    def test_dead_worker_retries_once_then_preserves_finished_rows(self):
        original=tests_background_ownership.BackgroundOwnershipTests();original.setUp()
        a=original.a;state=original.state(1);a._bg=state;a._bg_texts=[]
        a._async_request=('foreground request',7)
        a._async_background_request=('old background request',8)
        with patch.object(analysis_async,'background_step',side_effect=analysis_async.WorkerExitedError('exited')), \
                patch.object(analysis_async,'_error') as report:
            self.assertTrue(a._bg_step_once())
            self.assertIs(a._bg,state)
            self.assertEqual(a._bg['pos'],1)
            self.assertIsNone(a._async_background_request)
            self.assertEqual(a._async_request,('foreground request',7))
            report.assert_not_called()
            self.assertFalse(a._bg_step_once())
            self.assertIsNone(a._bg)
            self.assertEqual(a._bg_parked[state['owner']]['pos'],1)
            self.assertEqual(a._bg_parked[state['owner']]['results'][0],state['results'][0])
            report.assert_called_once_with(a)

    def test_engine_error_is_reported_without_retrying_the_bad_row(self):
        original=tests_background_ownership.BackgroundOwnershipTests();original.setUp()
        a=original.a;state=original.state(1);a._bg=state;a._bg_texts=[]
        a._async_request=('foreground request',7)
        a._async_background_request=('old background request',8)
        with patch.object(analysis_async,'background_step',side_effect=RuntimeError('engine failure')), \
                patch.object(analysis_async,'_error') as report:
            self.assertFalse(a._bg_step_once())
            self.assertIsNone(a._bg)
            self.assertIsNone(a._async_background_request)
            self.assertEqual(a._async_request,('foreground request',7))
            self.assertEqual(a._bg_parked[state['owner']]['pos'],1)
            self.assertNotIn('worker_restart_attempted',state)
            report.assert_called_once_with(a)

    def test_transport_exit_is_distinct_from_reported_engine_failure(self):
        import queue
        from analysis_worker import Worker,WorkerExitedError
        worker=Worker.__new__(Worker)
        worker.outbox=queue.Queue();worker.ready={};worker.closed=False;worker.process=Mock()
        worker.process.is_alive.return_value=False
        with self.assertRaises(WorkerExitedError):worker.poll(1)
        worker.process.is_alive.return_value=True
        worker.outbox.put((2,None,'original engine error'))
        with self.assertRaises(RuntimeError) as result:worker.poll(2)
        self.assertNotIsInstance(result.exception,WorkerExitedError)


if __name__=='__main__':unittest.main()
