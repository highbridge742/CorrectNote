"""Independent ownership checks for partial native initialization and teardown."""
import unittest
from unittest.mock import patch
import ime_candidates as S,ime_session as I,tsf_worker as T
from tests_tsf_worker_connection import native


class TSFConnectionFailureTests(unittest.TestCase):
    def test_already_initialized_apartment_still_balances_its_own_reference(self):
        with native() as (log,state),patch.object(S._ole32,'CoInitializeEx',return_value=1) as initialize:
            with T.worker_connection_scope() as owner:
                for _ in range(2):
                    with I.resource_scope():
                        with S.SearchCandidates() as obj:self.assertTrue(obj.available)
                self.assertEqual(initialize.call_count,1)
                self.assertNotIn(('uninitialize',),log)
            self.assertEqual(log.count(('uninitialize',)),1)
            self.assertEqual(log.count(('call',10,4)),1)

    def test_exception_after_partial_provider_allocation_retries_next_request(self):
        with native() as (log,state),T.worker_connection_scope() as owner:
            original=S._method
            def method(pointer,index,*signature):
                invoke=original(pointer,index,*signature)
                if index!=5:return invoke
                def failed(*args):
                    invoke(*args)
                    raise OSError('provider returned pointer then failed')
                return failed
            with patch.object(S,'_method',side_effect=method),I.resource_scope():
                with S.SearchCandidates() as failed:self.assertFalse(failed.available)
            self.assertIsNone(owner.borrow())
            self.assertEqual([x for x in log if x[0]=='release'],[('release',130),('release',120),('release',10)])
            self.assertEqual(log.count(('uninitialize',)),1)
            with I.resource_scope():
                with S.SearchCandidates() as recovered:self.assertTrue(recovered.available)
            self.assertIsNotNone(owner.borrow())

    def test_manager_teardown_failure_still_releases_com_and_clears_owner(self):
        with native() as (log,state):
            with T.worker_connection_scope() as owner:
                with I.resource_scope():
                    with S.SearchCandidates() as obj:self.assertTrue(obj.available)
                original=S._method
                def method(pointer,index,*signature):
                    if pointer.value==10 and index==4:
                        def failed(*args):raise OSError('deactivate failed')
                        return failed
                    return original(pointer,index,*signature)
                with patch.object(S,'_method',side_effect=method):owner.close()
                self.assertIsNone(owner.borrow())
                self.assertEqual(log.count(('release',10)),1)
                self.assertEqual(log.count(('uninitialize',)),1)
                owner.close()
                self.assertEqual(log.count(('uninitialize',)),1)
            self.assertIsNone(T.current_owner())

if __name__=='__main__':unittest.main()
