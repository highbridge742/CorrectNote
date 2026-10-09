"""Immutable optional preparation yields to input without retaining partial data."""
import unittest
from unittest.mock import Mock,patch
from analysis_context import request_scope,SupersededAnalysis
from analysis_worker import Runtime
import contextual_repair as R
import ngram_yomi as N
from context_vec import ContextVectorStore


class ResourcePrewarmTests(unittest.TestCase):
    def setUp(self):
        self.old_bigrams=N._BIGRAMS
        N._BIGRAMS=None
        R._seed_context.cache_clear()

    def tearDown(self):
        N._BIGRAMS=self.old_bigrams
        R._seed_context.cache_clear()

    def test_extra_resources_are_only_optional_stages(self):
        calls=[];runtime=Runtime();runtime.prepare_tables=Mock()
        runtime.prepare=Mock(return_value={})
        with patch.object(R,'_native_written_nominal_readings',side_effect=lambda:calls.append('native')),\
             patch.object(N,'_bigram_counts',side_effect=lambda:calls.append('bigram')),\
             patch.object(R,'_seed_context',side_effect=lambda:calls.append('context')):
            runtime.execute(dict(kind='prepare',lines=['資料']))
            self.assertEqual(calls,[])
            with patch('familiar_nominal.families'),patch('corrector._table_readings_for_surface'),patch('oddness._load'):
                runtime.execute(dict(kind='quick_prepare'))
            self.assertEqual(calls,[])
            runtime.execute(dict(kind='warmup'))
            self.assertEqual(calls,['native','bigram','context'])

    def test_cancelled_bigram_build_is_not_published_and_retry_is_exact(self):
        expected=N._bigram_counts();N._BIGRAMS=None
        original=N.TRIGRAMS;visits=[]
        class ObservedTable:
            def items(self):
                for item in original.items():
                    visits.append(None)
                    yield item
        for limit in (1,514,len(original)):
            with self.subTest(entries=limit):
                visits.clear()
                with patch.object(N,'TRIGRAMS',ObservedTable()),request_scope(lambda:len(visits)>=limit):
                    with self.assertRaises(SupersededAnalysis):N._bigram_counts()
                self.assertGreaterEqual(len(visits),limit)
                self.assertLessEqual(len(visits),limit+511)
                self.assertIsNone(N._BIGRAMS)
        self.assertEqual(N._bigram_counts(),expected)
        completed=N._BIGRAMS
        with patch.object(N,'TRIGRAMS',None):
            self.assertIs(N._bigram_counts(),completed)

    def test_cancelled_seed_build_never_exposes_partial_store(self):
        original=ContextVectorStore.observe_line
        initial_observations=[]
        def count_initial(store,words):
            initial_observations.append(None)
            return original(store,words)
        expected=ContextVectorStore()
        with patch.object(ContextVectorStore,'observe_line',count_initial):expected.ensure_seeded()
        for limit in (1,8,len(initial_observations)):
            with self.subTest(observations=limit):
                observed=[]
                def observe(store,words):
                    observed.append(store)
                    return original(store,words)
                with patch.object(ContextVectorStore,'observe_line',observe),\
                     patch.object(ContextVectorStore,'save',side_effect=AssertionError('No saves')),\
                     request_scope(lambda:len(observed)>=limit):
                    with self.assertRaises(SupersededAnalysis):R._seed_context()
                self.assertEqual(len(observed),limit)
                self.assertEqual(R._seed_context.cache_info().currsize,0)
                self.assertFalse(observed[0].seeded)
                complete=R._seed_context()
                self.assertIsNone(complete.path)
                self.assertEqual(complete._co,expected._co)
                self.assertEqual(complete._totals,expected._totals)
                self.assertEqual((complete.seeded,complete.seed_version),(expected.seeded,expected.seed_version))
                with patch.object(ContextVectorStore,'observe_line',side_effect=AssertionError('No repeated seeding')):
                    self.assertIs(R._seed_context(),complete)
                R._seed_context.cache_clear()

    def test_default_seed_initialization_ignores_request_cancellation(self):
        # The callback is explicit only for the private disposable cache build.
        # Existing shared runtime state initialization retains its old behavior.
        with request_scope(lambda:True):
            context=ContextVectorStore()
            self.assertTrue(context.ensure_seeded())
        self.assertTrue(context.seeded)
        self.assertTrue(context._co)

    def test_interrupted_warmup_reuses_completed_earlier_resource(self):
        runtime=Runtime();runtime.prepare_tables=Mock()
        seen=[];original=ContextVectorStore.observe_line
        def observe(store,words):
            seen.append(None)
            return original(store,words)
        with patch.object(R,'_native_written_nominal_readings',return_value={}),\
             patch.object(ContextVectorStore,'observe_line',observe),\
             request_scope(lambda:len(seen)>=3):
            with self.assertRaises(SupersededAnalysis):runtime.execute(dict(kind='warmup'))
        self.assertEqual(len(seen),3)
        complete=N._BIGRAMS
        self.assertIsNotNone(complete)
        self.assertEqual(R._seed_context.cache_info().currsize,0)
        with patch.object(R,'_native_written_nominal_readings',return_value={}),patch.object(N,'TRIGRAMS',None):
            runtime.execute(dict(kind='warmup'))
        self.assertIs(N._BIGRAMS,complete)
        self.assertEqual(R._seed_context.cache_info().currsize,1)


if __name__=='__main__':unittest.main()
