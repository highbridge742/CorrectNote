# -*- coding: utf-8 -*-
"""Use first IME composition time without analysing preedit text or repeating preparation."""
import unittest
from unittest.mock import patch
import tests_quick_async as base
import quick_analysis as Q

class QuickCompositionPrepareTests(base.QuickAsyncTests):
    def test_first_composition_prepares_once_even_as_preedit_changes(self):
        self.composing.return_value=True;Q.start(self.app)
        self.assertEqual(self.worker.submit.call_args[0][0],{'kind':'quick_prepare'})
        self.assertIsNone(getattr(self.app,'_quick_job',None));self.app._finish_quick_analysis.assert_not_called()
        self.edit('別の未確定');Q.start(self.app)
        self.assertEqual(self.worker.submit.call_count,1);self.assertEqual(self.snapshot.call_count,1)
    def test_committed_state_gets_a_fresh_snapshot_after_preparation(self):
        self.composing.return_value=True;Q.start(self.app)
        self.app._analysis_state_revision=1;self.edit('確定した文');self.composing.return_value=False;Q.start(self.app)
        self.assertEqual(self.worker.submit.call_args[0][0]['kind'],'quick')
        self.assertEqual(self.snapshot.call_count,2);self.worker.poll.assert_called_once_with(2)
        self.worker.poll.return_value=self.completed();Q.start(self.app);self.app._finish_quick_analysis.assert_called_once()
    def test_optional_preparation_failure_is_not_repeated_by_the_timer(self):
        self.composing.return_value=True;self.worker.submit.side_effect=[RuntimeError('prepare failed'),1]
        with patch.object(Q.traceback,'print_exc') as report:
            Q.start(self.app);Q.start(self.app);report.assert_called_once()
        self.assertEqual(self.worker.submit.call_count,1)
        self.composing.return_value=False;Q.start(self.app)
        self.assertEqual(self.worker.submit.call_count,2);self.app.status.config.assert_not_called()
    def test_close_allows_preparation_in_a_new_quick_window(self):
        self.composing.return_value=True;Q.start(self.app);Q.close(self.app)
        self.assertFalse(self.app._quick_composition_prepared)
        Q.start(self.app);self.assertEqual(self.worker.submit.call_count,2)
    def test_preparation_does_not_correct_text_or_request_ime(self):
        from analysis_worker import Runtime
        with patch('familiar_nominal.families') as families,patch('oddness._load') as words,patch('corrector.correct_line',side_effect=AssertionError('no input')):
            self.assertIsNone(Runtime().execute({'kind':'quick_prepare'}))
        families.assert_called_once_with();words.assert_called_once_with()

if __name__=='__main__':unittest.main()
