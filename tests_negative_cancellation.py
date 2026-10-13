import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import morphology as M
from analysis_context import request_scope,SupersededAnalysis

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class NegativeCancellationTests(unittest.TestCase):
    def test_superseded_entry_never_queries_dictionary(self):
        with request_scope(lambda:True),patch.object(M._TOKENIZER.sys_dic,'lookup') as lookup:
            with self.assertRaises(SupersededAnalysis):M.native_dependent_noun_ending_possible('量がまし')
        lookup.assert_not_called()

    def test_long_suffix_walk_has_bounded_frequent_checkpoints(self):
        pending=False;seen=[]
        def lookup(*args):
            nonlocal pending
            seen.append(args[0]);pending=True
            return []
        with request_scope(lambda:pending),patch.object(M._TOKENIZER.sys_dic,'lookup',side_effect=lookup):
            with self.assertRaises(SupersededAnalysis):M.native_dependent_noun_ending_possible('資'*3999)
        self.assertGreater(len(seen),0)
        self.assertLessEqual(len(seen),64)

    def test_last_positive_publication_is_unconditionally_checked(self):
        pending=False
        def extra(*args):
            nonlocal pending
            pending=True
            return ('名詞,非自立,一般,*',)
        with request_scope(lambda:pending,poll_interval=100),patch.object(M._TOKENIZER.sys_dic,'lookup',return_value=[(0,'と')]),patch.object(M._TOKENIZER.sys_dic,'lookup_extra',side_effect=extra):
            with self.assertRaises(SupersededAnalysis):M.native_dependent_noun_ending_possible('と')

    def test_last_negative_publication_is_unconditionally_checked(self):
        pending=False
        def lookup(*args):
            nonlocal pending
            pending=True
            return []
        with request_scope(lambda:pending,poll_interval=100),patch.object(M._TOKENIZER.sys_dic,'lookup',side_effect=lookup):
            with self.assertRaises(SupersededAnalysis):M.native_dependent_noun_ending_possible('量')

    def test_native_failure_does_not_hide_request_supersession(self):
        for failure in (ValueError('synthetic failure'),SystemExit(1),SupersededAnalysis()):
            pending=False
            def lookup(*args):
                nonlocal pending
                pending=True
                raise failure
            with self.subTest(failure=type(failure).__name__),request_scope(lambda:pending,poll_interval=100),patch.object(M._TOKENIZER.sys_dic,'lookup',side_effect=lookup):
                with self.assertRaises(SupersededAnalysis):M.native_dependent_noun_ending_possible('量')

    def test_cancellation_releases_lock_for_another_thread_and_next_request(self):
        pending=False
        def lookup(*args):
            nonlocal pending
            pending=True
            return []
        with request_scope(lambda:pending),patch.object(M._TOKENIZER.sys_dic,'lookup',side_effect=lookup):
            with self.assertRaises(SupersededAnalysis):M.native_dependent_noun_ending_possible('量')
        def acquire():
            locked=M._TOKENIZE_LOCK.acquire(timeout=1)
            if locked:M._TOKENIZE_LOCK.release()
            return locked
        with ThreadPoolExecutor(max_workers=1) as pool:self.assertTrue(pool.submit(acquire).result(timeout=2))
        with request_scope(lambda:False):self.assertIs(M.native_dependent_noun_ending_possible('量'),False)

if __name__=='__main__':unittest.main()
