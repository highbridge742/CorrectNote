"""Demand preparation preserves native evidence and yields optional work to input."""
import unittest
from unittest.mock import Mock,patch
from contextlib import ExitStack
from analysis_worker import Runtime
from analysis_context import request_scope,SupersededAnalysis
import reading_likelihood as L
import ngram_yomi as N

class DemandPreparationTests(unittest.TestCase):
    def test_common_prepare_and_quick_prepare_do_not_load_unused_resources(self):
        with ExitStack() as stack:
            for path in ('familiar_nominal.families','corrector._table_readings_for_surface','seed_japanese.available','oddness._load'):
                stack.enter_context(patch(path))
            english=stack.enter_context(patch('loanword._english_seed',side_effect=AssertionError('optional english')))
            likelihood=stack.enter_context(patch.object(L,'_distributions',side_effect=AssertionError('optional likelihood')))
            runtime=Runtime();runtime.prepare=Mock(return_value={'context':{}})
            self.assertEqual(runtime.execute(dict(kind='prepare',lines=['資料'])),{'context':{}})
            runtime.execute(dict(kind='quick_prepare'))
            english.assert_not_called();likelihood.assert_not_called()
            self.assertTrue(runtime.tables_ready)

    def test_optional_resources_are_kept_in_warmup_and_yield_between_stages(self):
        for cancel in (False,True):
            calls=[];runtime=Runtime();runtime.prepare_tables=Mock()
            with ExitStack() as stack:
                for path,label in [('loanword._english_seed','english'),('reading_likelihood._distributions','reading'),('contextual_repair._native_written_nominal_readings','native'),('ngram_yomi._bigram_counts','bigrams'),('contextual_repair._seed_context','context')]:
                    stack.enter_context(patch(path,side_effect=lambda label=label:calls.append(label)))
                with request_scope(lambda:cancel and calls==['english']):
                    if cancel:
                        with self.assertRaises(SupersededAnalysis):runtime.execute(dict(kind='warmup'))
                    else:runtime.execute(dict(kind='warmup'))
            self.assertEqual(calls,['english'] if cancel else ['english','reading','native','bigrams','context'])

    def test_cancelled_distribution_never_publishes_partial_evidence(self):
        original=N.TRIGRAMS;L._distributions.cache_clear()
        self.addCleanup(L._distributions.cache_clear)
        expected=L._distributions();L._distributions.cache_clear()
        seen=[]
        class Table:
            def items(self):
                for item in original.items():
                    seen.append(None);yield item
        for limit in (1,514,len(original)):
            seen.clear()
            with self.subTest(limit=limit),patch.object(N,'TRIGRAMS',Table()),request_scope(lambda:len(seen)>=limit):
                with self.assertRaises(SupersededAnalysis):L._distributions()
            self.assertGreaterEqual(len(seen),limit);self.assertLessEqual(len(seen),limit+511)
            self.assertEqual(L._distributions.cache_info().currsize,0)
        self.assertEqual(L._distributions(),expected)
        with patch.object(N,'TRIGRAMS',None):self.assertIs(L._distributions(),L._distributions())

    def test_distribution_cancellation_is_checked_before_table_walk(self):
        L._distributions.cache_clear();self.addCleanup(L._distributions.cache_clear)
        with patch.object(N,'TRIGRAMS',None),request_scope(lambda:True):
            with self.assertRaises(SupersededAnalysis):L._distributions()
        self.assertEqual(L._distributions.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
