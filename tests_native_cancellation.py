# -*- coding: utf-8 -*-
"""Obsolete grammar searches stop before starting another native parse."""
import unittest
from unittest.mock import patch
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import morphology as M
from analysis_context import request_scope,SupersededAnalysis

@unittest.skipUnless(M.HAS_JANOME,'native parser required')
class NativeCancellationTests(unittest.TestCase):
    def test_obsolete_request_does_not_enter_native_or_fallback(self):
        with patch.object(M._TOKENIZER,'tokenize',return_value=[]) as native,patch.object(M,'_tokenize_fallback') as fallback:
            with request_scope(lambda:True):
                with self.assertRaises(SupersededAnalysis):M._tokenize_janome('資料')
            native.assert_not_called();fallback.assert_not_called()

    def test_cancellation_unwinds_both_caches_and_next_request_can_parse(self):
        pending=False
        def check():return pending
        with patch.object(M._TOKENIZER,'tokenize',return_value=[]) as native:
            with self.assertRaises(SupersededAnalysis):
                with request_scope(check),M.tokenization_scope():
                    M._tokenize_janome('一つ目')
                    pending=True
                    M._tokenize_janome('二つ目')
            self.assertEqual(native.call_count,1)
            self.assertIsNone(M._TOKENIZATION_CACHE.get())
            self.assertIsNone(M._NATIVE_TOKENIZATION_CACHE.get())
            with request_scope(lambda:False),M.tokenization_scope():
                self.assertEqual(M._tokenize_janome('二つ目'),[])
            self.assertEqual(native.call_count,2)

    def test_request_callback_is_not_run_by_other_thread(self):
        with patch.object(M._TOKENIZER,'tokenize',return_value=[]) as native:
            def reject():raise AssertionError('callback belongs to requesting thread')
            with request_scope(reject):
                context=copy_context()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertEqual(pool.submit(context.run,M._tokenize_janome,'資料').result(),[])
            self.assertEqual(native.call_count,1)

    def test_native_failure_still_uses_fallback_for_current_request(self):
        for error in (ValueError('synthetic native failure'),SystemExit(1)):
            with self.subTest(error=type(error).__name__):
                with request_scope(lambda:False),patch.object(M._TOKENIZER,'tokenize',side_effect=error),patch.object(M,'_tokenize_fallback',return_value=[]) as fallback:
                    self.assertEqual(M._tokenize_janome('資料'),[])
                    fallback.assert_called_once_with('資料')

if __name__=='__main__':unittest.main()
