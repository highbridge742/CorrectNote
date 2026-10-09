# -*- coding: utf-8 -*-
"""Discarded background work stops while useful unrelated prefetch continues."""
import io,queue,unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app,analysis_async,analysis_context,analysis_worker


def owner():
    a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
    a.root=Mock();a._bg_start_job='start';a._bg_job='poll';a._bg=None
    a._bg_texts=['pending'];a._async_background_request=('obsolete',1)
    a._prefetch_worker=Mock();a._prefetch_worker.closed=False
    a._prefetch_worker.process.is_alive.return_value=True
    a._prefetch_worker_state=('unchanged model',)
    return a


class BackgroundCancellationTests(unittest.TestCase):
    def test_explicit_stop_cancels_only_the_discarded_worker_request(self):
        a=owner();a._correction_worker=Mock();a._quick_worker=Mock()
        a._stop_background_tabs()
        a._prefetch_worker.submit.assert_called_once_with({'kind':'cancel'})
        a._prefetch_worker.close.assert_not_called()
        a._correction_worker.submit.assert_not_called();a._quick_worker.submit.assert_not_called()
        self.assertEqual(a._prefetch_worker_state,('unchanged model',))
        self.assertIsNone(a._async_background_request);self.assertIsNone(a._bg_job)
        self.assertIsNone(a._bg_start_job);self.assertEqual(a._bg_texts,[])
        a._stop_background_tabs()
        self.assertEqual(a._prefetch_worker.submit.call_count,1)

    def test_idle_or_absent_worker_does_not_start_or_cancel_public_preparation(self):
        for mode in ('no_request','absent','dead','closed'):
            with self.subTest(mode=mode):
                a=owner();worker=a._prefetch_worker
                if mode=='no_request':a._async_background_request=None
                elif mode=='absent':a._prefetch_worker=None
                elif mode=='dead':worker.process.is_alive.return_value=False
                elif mode=='closed':worker.closed=True
                with patch.object(analysis_async,'Worker') as create:
                    a._stop_background_tabs()
                worker.submit.assert_not_called();create.assert_not_called()
                self.assertIsNone(a._async_background_request)

    def test_transport_failure_is_reported_but_scheduling_is_still_stopped(self):
        a=owner();a._prefetch_worker.submit.side_effect=RuntimeError('test closed transport')
        with redirect_stderr(io.StringIO()) as output:a._stop_background_tabs()
        self.assertIn('test closed transport',output.getvalue())
        self.assertIsNone(a._async_background_request);self.assertIsNone(a._bg_job)
        self.assertEqual(a._bg_texts,[])
        a._prefetch_worker.close.assert_not_called()

    def test_existing_worker_unwinds_discarded_task_without_emitting_a_result(self):
        a=owner();inbox=queue.Queue();outputs=[];released=[];executed=[];states=[]
        a._prefetch_worker.submit.side_effect=lambda task:inbox.put(dict(id=2,task=task,state=None))
        inbox.put(dict(id=1,task={'kind':'line'},state='initial'))
        # A deterministic empty source ends after the cancel has been consumed.
        class Inbox:
            def get(self):
                try:return inbox.get_nowait()
                except queue.Empty:return None
            def get_nowait(self):return inbox.get_nowait()
        class Runtime:
            def set_state(self,value):states.append(value)
            def execute(self,task):
                executed.append(task['kind'])
                try:
                    a._stop_background_tabs()
                    analysis_context.check_current_request()
                    return {'obsolete result':True}
                finally:released.append(True)
        with patch.object(analysis_worker,'Runtime',Runtime):
            analysis_worker._serve(Inbox(),SimpleNamespace(put=outputs.append))
        self.assertEqual(outputs,[]);self.assertEqual(executed,['line'])
        self.assertEqual(released,[True]);self.assertEqual(states,['initial'])
        self.assertIsNone(analysis_context._REQUEST_CHECK.get())


if __name__=='__main__':unittest.main()
