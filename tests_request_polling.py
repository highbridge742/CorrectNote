# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import analysis_context as A

class RequestPollingTests(unittest.TestCase):
    def test_frequent_checks_poll_first_then_after_interval(self):
        pending=False;calls=[]
        def check():calls.append(True);return pending
        with patch.object(A,'monotonic',side_effect=[10,10.001,10.004,10.005]):
            with A.request_scope(check,poll_interval=.005):
                A.check_current_request(frequent=True)
                pending=True
                A.check_current_request(frequent=True)
                A.check_current_request(frequent=True)
                with self.assertRaises(A.SupersededAnalysis):A.check_current_request(frequent=True)
        self.assertEqual(len(calls),2)
        self.assertIsNone(A._REQUEST_CHECK.get())

    def test_semantic_and_publication_check_never_wait_for_interval(self):
        pending=False
        def check():return pending
        with patch.object(A,'monotonic',return_value=10):
            with A.request_scope(check,poll_interval=.005):
                A.check_current_request(frequent=True);pending=True
                with self.assertRaises(A.SupersededAnalysis):A.check_current_request()

    def test_new_request_and_nested_request_get_fresh_first_poll(self):
        with patch.object(A,'monotonic',return_value=10):
            with A.request_scope(lambda:False,poll_interval=.005):
                A.check_current_request(frequent=True);outer=A._REQUEST_CHECK.get()
                with A.request_scope(lambda:True,poll_interval=.005):
                    with self.assertRaises(A.SupersededAnalysis):A.check_current_request(frequent=True)
                self.assertIs(A._REQUEST_CHECK.get(),outer)
            with A.request_scope(lambda:True,poll_interval=.005):
                with self.assertRaises(A.SupersededAnalysis):A.check_current_request(frequent=True)

    def test_default_scope_checks_every_frequent_boundary_without_clock(self):
        calls=[]
        with patch.object(A,'monotonic',side_effect=AssertionError('clock not needed')):
            with A.request_scope(lambda:calls.append(True)):
                for i in range(3):A.check_current_request(frequent=True)
        self.assertEqual(len(calls),3)

if __name__=='__main__':unittest.main()
