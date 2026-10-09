# -*- coding: utf-8 -*-
"""Open optional TSF evidence only after the existing first-conversion test needs it."""
from contextlib import ExitStack,contextmanager
from types import SimpleNamespace
from unittest.mock import patch,Mock
import unittest
import ime_inverse_gate as I

class LazySearchTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.cache={};token=I._CORRECTION_CACHE.set(self.cache)
        self.addCleanup(I._CORRECTION_CACHE.reset,token)
        self.events=[];self.field='異ぬ';self.reading='いぬ'
        self.first=SimpleNamespace(available=True,
            reverse_words=Mock(return_value=None),phonetic=Mock(return_value=self.reading),
            convert=Mock(return_value=self.field))
        self.search=SimpleNamespace(available=True,candidates=Mock(return_value=(self.field,)))
        @contextmanager
        def first():
            self.events.append('open-first')
            try:yield self.first
            finally:self.events.append('close-first')
        @contextmanager
        def search():
            self.events.append('open-search')
            try:yield self.search
            finally:self.events.append('close-search')
        self.search_factory=self.stack.enter_context(patch('ime_candidates.SearchCandidates',side_effect=search))
        self.stack.enter_context(patch('ime_language.JapaneseIME',side_effect=first))
        for name,value in [('reading_segments.native_paused_nominal_ranges',()),
                ('reading_segments.native_mixed_kana_word_ranges',()),
                ('reading_segments.native_lexical_phrase',False),
                ('pos_grammar.prolonged_quotative',False),
                ('kanji_guess.ime_readings_for',()),('analysis_work.occurrence_readings',()),
                ('ime_inverse_gate._source_readings',()),
                ('ime_inverse_gate._native_argument_prefix',0),
                ('pos_grammar.odd_kana_spans',[(0,1)])]:
            self.stack.enter_context(patch(name,return_value=value))
    def call(self,source=None):
        source=self.field+'。' if source is None else source
        def tokens(text):return [(text,'名詞:一般','',0,len(text),False,'')]
        return I.anomalous_source_fields(source,tokens,object(),object())
    def test_first_conversion_match_keeps_evidence_without_opening_unused_search(self):
        self.assertEqual(self.call(),((0,2,self.reading),))
        self.search_factory.assert_not_called();self.search.candidates.assert_not_called()
        self.assertEqual(self.cache['source_readings',self.field],((self.reading,True),))
        self.assertEqual(self.events,['open-first','close-first'])
    def test_missing_hypotheses_do_not_open_a_search_without_a_reading(self):
        self.first.phonetic.return_value=None
        self.assertEqual(self.call(),())
        self.search_factory.assert_not_called()
        self.assertEqual(self.cache[self.field+'。'],())
    def test_first_mismatch_keeps_exact_membership_and_weaker_provenance(self):
        self.first.convert.return_value='別ぬ'
        self.assertEqual(self.call(),((0,2,self.reading),))
        self.search.candidates.assert_called_once_with(self.reading)
        self.assertEqual(self.cache['source_readings',self.field],((self.reading,False),))
        self.assertEqual(self.events,['open-first','open-search','close-search','close-first'])
    def test_multiple_fields_share_one_late_search_and_reject_absent_membership(self):
        self.first.convert.return_value='別ぬ';self.search.candidates.return_value=('別ぬ',)
        self.assertEqual(self.call(self.field+'。'+self.field+'。'),())
        self.search_factory.assert_called_once();self.assertEqual(self.search.candidates.call_count,2)
        self.assertNotIn(('source_readings',self.field),self.cache)
    def test_no_first_interface_retains_search_fallback_and_no_both_unavailable_cache(self):
        self.first.available=False
        with patch.object(I,'_source_readings',return_value=(self.reading,)):
            self.assertEqual(self.call(),((0,2,self.reading),))
        self.first.reverse_words.assert_not_called();self.first.phonetic.assert_not_called()
        self.first.convert.assert_not_called();self.search.candidates.assert_called_once_with(self.reading)
        self.cache.clear();self.search.available=False
        self.assertEqual(self.call(),());self.assertFalse(self.cache)
    def test_failed_search_and_cancellation_release_the_owned_interfaces(self):
        self.first.convert.return_value='別ぬ';self.search.candidates.side_effect=ValueError('unavailable')
        self.assertEqual(self.call(),())
        self.assertEqual(self.events[-2:],['close-search','close-first'])
        self.cache.clear();self.events.clear();self.search_factory.reset_mock()
        from analysis_context import SupersededAnalysis
        with patch('analysis_context.check_current_request',side_effect=SupersededAnalysis):
            with self.assertRaises(SupersededAnalysis):self.call()
        self.search_factory.assert_not_called();self.assertEqual(self.events,['open-first','close-first'])
        self.assertNotIn(self.field+'。',self.cache)

if __name__=='__main__':unittest.main()
