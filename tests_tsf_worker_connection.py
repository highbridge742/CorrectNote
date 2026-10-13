import ctypes as C
import queue,unittest
from contextlib import ExitStack,contextmanager
from contextvars import copy_context
from threading import Thread,get_ident
from unittest.mock import patch,Mock
import ime_candidates as S,ime_session as I,tsf_worker as T
from analysis_context import request_scope,SupersededAnalysis


@contextmanager
def native():
    log=[];state=dict(provider_ok=True,search_ok=True,activate_ok=True,generation=0,release_error=False)
    def initialize(*args):log.append(('initialize',));return 0
    def create(*args):args[-1]._obj.value=10;log.append(('create',));return 0
    def release(pointer):
        if pointer:log.append(('release',pointer.value))
        if pointer and state['release_error'] and pointer.value>=30:raise OSError('release')
    def method(pointer,index,*signature):
        def invoke(*args):
            log.append(('call',pointer.value,index))
            if pointer.value==10 and index==3:return 0 if state['activate_ok'] else -1
            if pointer.value==10 and index==11:
                state['generation']+=1
                if not state['provider_ok']:return -1
                args[-1]._obj.value=20+state['generation']*100;return 0
            if index==5 and pointer.value%100==20:
                if not state['search_ok']:return -1
                args[-1]._obj.value=30+state['generation']*100;return 0
            return 0
        return invoke
    with ExitStack() as stack:
        stack.enter_context(patch.object(S._ole32,'CoInitializeEx',side_effect=initialize))
        stack.enter_context(patch.object(S._ole32,'CoCreateInstance',side_effect=create))
        stack.enter_context(patch.object(S._ole32,'CoUninitialize',side_effect=lambda:log.append(('uninitialize',))))
        stack.enter_context(patch.object(S,'_method',side_effect=method))
        stack.enter_context(patch.object(S,'_release',side_effect=release))
        yield log,state


class WorkerConnectionTests(unittest.TestCase):
    def test_candidate_results_do_not_cross_requests_and_partial_failure_discards_manager(self):
        from tests_search_candidate_cache import SearchCandidateCacheTests
        fixture=SearchCandidateCacheTests()
        for failed in (dict(values=['話','離'],missing_items={1}),dict(count_hr=-1),dict(query_hr=-1)):
            with self.subTest(failed=failed),fixture.native([dict(values=['話','離','話']),dict(values=['離','話']),failed]) as calls:
                connection=Mock()
                with T.worker_connection_scope() as owner:
                    owner.publish(connection)
                    for index in range(3):
                        with I.resource_scope():
                            obj=fixture.resource();_,obj._retained=I.retain(obj)
                            obj._connection=connection;obj._connection_owner=owner
                            self.assertFalse(obj._candidate_cache)
                            result=obj.candidates('はな')
                            if index==0:self.assertEqual(result,('話','離','話'))
                            elif index==1:self.assertEqual(result,('離','話'))
                        self.assertEqual(obj._candidate_cache,{})
                        if index<2:self.assertIs(owner.borrow(),connection)
                    self.assertIsNone(owner.borrow());connection.close.assert_called_once()
                self.assertEqual(calls['queries'],['はな','はな','はな'])
                self.assertCountEqual(calls['freed'],calls['allocated'])

    @unittest.skipUnless(__import__('sys').platform=='win32','Windows messages')
    def test_real_thread_message_quit_is_consumed_without_other_threads(self):
        from ctypes import wintypes as W
        user=C.WinDLL('user32',use_last_error=True);kernel=C.WinDLL('kernel32',use_last_error=True)
        user.PostThreadMessageW.argtypes=(W.DWORD,W.UINT,W.WPARAM,W.LPARAM)
        user.PostThreadMessageW.restype=W.BOOL
        kernel.GetCurrentThreadId.restype=W.DWORD
        results=[];errors=[]
        def run():
            try:
                self.assertTrue(T._pump_messages())  # Create this new thread's queue.
                identifier=kernel.GetCurrentThreadId()
                self.assertTrue(user.PostThreadMessageW(identifier,0x8000,0,0))
                self.assertTrue(T._pump_messages())
                self.assertTrue(user.PostThreadMessageW(identifier,0x0012,0,0))
                with T.worker_connection_scope() as owner:
                    owner.connection=Mock()
                    self.assertIsNone(owner.get(Mock()));self.assertTrue(owner.quit)
                results.append('quit consumed')
            except BaseException as exc:errors.append(exc)
        thread=Thread(target=run);thread.start();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(results,['quit consumed'])

    def test_manager_only_survives_and_providers_results_refresh_every_request(self):
        with native() as (log,state):
            with T.worker_connection_scope() as owner:
                objects=[]
                for index in range(3):
                    with I.resource_scope():
                        with S.SearchCandidates() as obj:
                            self.assertTrue(obj.available);objects.append(obj)
                            obj._candidate_cache['synthetic']=('result',)
                            with S.SearchCandidates() as same:self.assertIs(same,obj)
                    self.assertEqual(obj._candidate_cache,{})
                    self.assertFalse(obj.available);self.assertIsNone(obj._connection)
                    connection=owner.borrow()
                    self.assertEqual(set(vars(connection)),{'owner','manager','active','com'})
                    self.assertTrue(connection.manager)
                self.assertEqual(len({id(o) for o in objects}),3)
                self.assertEqual(log.count(('initialize',)),1)
                self.assertEqual(log.count(('call',10,3)),1)
                self.assertEqual(log.count(('call',10,11)),3)
                self.assertNotIn(('call',10,4),log)
            self.assertEqual(log.count(('call',10,4)),1)
            self.assertEqual(log.count(('release',10)),1)
            self.assertEqual(log.count(('uninitialize',)),1)
            self.assertEqual([r for r in log if r[0]=='release' and r[1]!=10],
                             [('release',130),('release',120),('release',230),('release',220),('release',330),('release',320)])

    def test_no_worker_scope_retains_previous_request_close_contract(self):
        with native() as (log,state):
            for _ in range(2):
                with I.resource_scope():
                    with S.SearchCandidates() as obj:self.assertTrue(obj.available)
            self.assertEqual(log.count(('call',10,3)),2)
            self.assertEqual(log.count(('call',10,4)),2)

    def test_initialization_and_later_provider_failure_are_not_retained(self):
        for failure in ('activate_ok','provider_ok','search_ok'):
            with self.subTest(failure=failure),native() as (log,state):
                with T.worker_connection_scope() as owner:
                    state[failure]=False
                    with I.resource_scope():
                        with S.SearchCandidates() as obj:self.assertFalse(obj.available)
                    self.assertIsNone(owner.borrow())
                    state[failure]=True
                    with I.resource_scope():
                        with S.SearchCandidates() as obj:self.assertTrue(obj.available)
                    self.assertIsNotNone(owner.borrow())
                    state['provider_ok']=False
                    with I.resource_scope():
                        with S.SearchCandidates() as obj:self.assertFalse(obj.available)
                    self.assertIsNone(owner.borrow())
                    state['provider_ok']=True
                    with I.resource_scope():
                        with S.SearchCandidates() as obj:self.assertTrue(obj.available)

    def test_cancellation_exception_and_cleanup_error_discard_connection(self):
        for failure in ('cancel','exception','release'):
            with self.subTest(failure=failure),native() as (log,state):
                with T.worker_connection_scope() as owner:
                    try:
                        with I.resource_scope():
                            with S.SearchCandidates() as obj:
                                obj._candidate_cache['synthetic']=('result',)
                                if failure=='cancel':raise SupersededAnalysis()
                                if failure=='exception':raise ValueError('body')
                                state['release_error']=True
                    except (SupersededAnalysis,ValueError):pass
                    self.assertEqual(obj._candidate_cache,{})
                    self.assertIsNone(owner.borrow())
                    self.assertIn(('uninitialize',),log)

    def test_cancel_before_enter_or_during_initialization_never_keeps_resources(self):
        with native() as (log,state),T.worker_connection_scope() as owner:
            with patch('analysis_context.check_current_request',side_effect=SupersededAnalysis):
                with self.assertRaises(SupersededAnalysis):S.SearchCandidates().__enter__()
            self.assertEqual(log,[])
            with patch('analysis_context.check_current_request',side_effect=[None,SupersededAnalysis()]):
                with self.assertRaises(SupersededAnalysis):
                    with I.resource_scope():S.SearchCandidates().__enter__()
            self.assertIsNone(owner.borrow());self.assertIn(('uninitialize',),log)

    def test_copied_context_cannot_borrow_or_close_foreign_manager(self):
        with native() as (log,state),T.worker_connection_scope() as owner:
            with I.resource_scope():
                with S.SearchCandidates() as obj:pass
            connection=owner.borrow();context=copy_context();results=[]
            def run():
                results.append(T.current_owner())
                for action in (owner.borrow,connection.close):
                    try:action()
                    except RuntimeError:results.append('rejected')
            thread=Thread(target=lambda:context.run(run));thread.start();thread.join(3)
            self.assertFalse(thread.is_alive());self.assertEqual(results,[None,'rejected','rejected'])
            self.assertTrue(owner.borrow().manager)

    def test_wait_pumps_thread_messages_and_preserves_queue_shutdown(self):
        class Inbox:
            def __init__(self):self.calls=[]
            def get(self,**kw):
                self.calls.append(kw)
                if len(self.calls)==1:raise queue.Empty()
                return {'id':1}
        with T.worker_connection_scope() as owner:
            owner.connection=Mock();inbox=Inbox()
            with patch.object(T,'_pump_messages',return_value=True) as pump:
                self.assertEqual(owner.get(inbox),{'id':1});self.assertEqual(pump.call_count,2)
            self.assertEqual(inbox.calls,[{'timeout':.02},{'timeout':.02}])
            with patch.object(T,'_pump_messages',return_value=False):
                self.assertIsNone(owner.get(Mock()));self.assertTrue(owner.quit)
            self.assertFalse(owner.pump())

    def test_serve_shutdown_and_body_failure_close_scope_on_owner_thread(self):
        import analysis_worker as W
        class Inbox:
            def get(self):return None
        with patch.object(T._Owner,'close',autospec=True) as close:
            W._serve(Inbox(),Mock());close.assert_called_once()
        with patch.object(T._Owner,'close',autospec=True) as close,patch.object(W,'_serve_requests',side_effect=ValueError('serve')):
            with self.assertRaises(ValueError):W._serve(Inbox(),Mock())
            close.assert_called_once()

if __name__=='__main__':unittest.main()
