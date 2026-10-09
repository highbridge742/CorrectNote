# -*- coding: utf-8 -*-
"""Completed source-evidence phases relinquish an obsolete input request."""
import sys
import unittest
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

import analysis_context as A
import analysis_worker as W
import contextual_repair as Q
import context_meaning as CM
import corrector as C
import ime_inverse_gate as G
import ime_session as I
import morphology as M
import oddness as O


class TargetCancellationTests(unittest.TestCase):
    def test_obsolete_target_request_stops_before_reading_source_evidence(self):
        with patch.object(M,'original_spelling_facts',side_effect=AssertionError('obsolete source read')) as facts:
            with A.request_scope(lambda:True),self.assertRaises(A.SupersededAnalysis):
                Q.targets_for_line('資料を保存した。',None,None,None)
        facts.assert_not_called()
        self.assertIsNone(A._REQUEST_CHECK.get())

    def _assert_completed_phase_relinquishes_request(self,phase):
        from tests_analysis_async import initial
        from last_choice import set_active
        import charngram,ngram_yomi,units
        runtime=W.Runtime();runtime.set_state(W.snapshot(initial()));runtime.prepare_tables()
        Q._seed_context();ngram_yomi._bigram_counts();charngram._load()
        old=('処理がじゃのになっていないだろうか\t' if phase=='meaning' else
             '補正が適用されるのを舞ってられないので、')
        latest='資料を保存しました。'
        old_context=runtime.execute(dict(kind='prepare',lines=[old]))
        current=runtime.execute(dict(kind='prepare',lines=[latest]))
        task=dict(kind='line',line=latest,input_method='kana',context=current['context'],attested=current['attested'])
        stale=False;after_arrival=[];completed_targets=[]
        module,name=(CM,'anomalous_frames') if phase=='meaning' else (O,'is_odd_run')
        original=getattr(module,name);native=M._tokenize_janome_uncached;targets=Q.targets_for_line
        def completed_evidence(*args,**kwargs):
            nonlocal stale
            caller=sys._getframe(1)
            direct=caller.f_code.co_name=='targets_for_line' and caller.f_code.co_filename==Q.__file__
            value=original(*args,**kwargs)
            if direct and args[0]==old and not kwargs.get('skip_join'):stale=True
            return value
        def parsed(*args,**kwargs):
            if stale:after_arrival.append(args[0])
            return native(*args,**kwargs)
        def collected(*args,**kwargs):
            value=targets(*args,**kwargs);completed_targets.append(value);return value
        def model():
            return deepcopy((runtime.store.to_list(),runtime.store.revision(),
                runtime.choices._readings,runtime.choices._units,runtime.choices.revision(),
                runtime.ime._pairs,runtime.decisions._protected,runtime.decisions._rejected,
                runtime.decisions._odd_only,charngram._LEARNED,runtime.context_vec._co))
        try:
            with ExitStack() as guards:
                for store in (runtime.store,runtime.choices,runtime.ime,runtime.decisions,runtime.context_vec):
                    guards.enter_context(patch.object(store,'save',side_effect=AssertionError('analysis tried to save')))
                guards.enter_context(patch.object(runtime.choices,'record',side_effect=AssertionError('analysis tried to learn a choice')))
                guards.enter_context(patch.object(runtime.ime,'remember',side_effect=AssertionError('analysis tried to retain input')))
                guards.enter_context(patch.object(charngram,'learn',side_effect=AssertionError('analysis tried to learn text')))
                guards.enter_context(patch.object(charngram,'save',side_effect=AssertionError('analysis tried to save text')))
                expected=runtime.execute(task);before=model()
                with patch.object(module,name,completed_evidence),patch.object(M,'_tokenize_janome_uncached',parsed),patch.object(Q,'targets_for_line',collected),patch.object(units,'build_line_units') as display,patch.object(units,'build_suspect_units') as suspect:
                    with A.request_scope(lambda:stale),self.assertRaises(A.SupersededAnalysis):
                        runtime.execute(dict(kind='line',line=old,input_method='kana',context=old_context['context'],attested=old_context['attested']))
                    self.assertTrue(stale)
                    self.assertEqual(after_arrival,[])
                    self.assertEqual(completed_targets,[])
                    display.assert_not_called();suspect.assert_not_called()
                self.assertEqual(model(),before)
                for value in (Q._SEARCH.get(),C._CORRECTION_SOURCE.get(),G._CORRECTION_CACHE.get(),
                              M._TOKENIZATION_CACHE.get(),I._CURRENT.get(),A._REQUEST_CHECK.get(),runtime._ime_queries):
                    self.assertIsNone(value)
                self.assertEqual(C._CORRECTION_PATH.get(),())
                with A.request_scope(lambda:False):actual=runtime.execute(task)
                self.assertEqual(actual,expected);self.assertEqual(model(),before)
                self.assertEqual(actual['result']['original'],latest)
                self.assertEqual(actual['result']['analysis_status'],'complete')
                for key in ('original_units','corrected_units'):
                    text,rows=actual[key];self.assertEqual(text,latest)
                    for row in rows:self.assertEqual(text[row['start']:row['end']],row['text'])
        finally:set_active(None)

    def test_completed_meaning_evidence_cancels_before_later_target_phases(self):
        self._assert_completed_phase_relinquishes_request('meaning')

    def test_completed_source_oddness_cancels_before_later_target_phases(self):
        self._assert_completed_phase_relinquishes_request('oddness')


if __name__=='__main__':unittest.main()
