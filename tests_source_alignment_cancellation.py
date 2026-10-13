# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
import contextvars,difflib,threading,unittest
from unittest.mock import patch
import corrector as C
from analysis_context import request_scope,SupersededAnalysis
from ime_session import resource_scope,retain


class AlignmentCheckpointTests(unittest.TestCase):
    def test_views_leave_stdlib_matching_blocks_and_opcodes_identical(self):
        strings=('','a','aa','aba','acab','ababa','baaba','資料abc','💡e\u0301\tab','\t⇒外','文'*80)
        for original in strings:
            for current in strings:
                expected=difflib.SequenceMatcher(None,original,current,autojunk=False)
                actual=difflib.SequenceMatcher(None,C._SourceRangeText(original),C._SourceRangeText(current),autojunk=False)
                self.assertEqual(actual.get_matching_blocks(),expected.get_matching_blocks(),(original,current))
                self.assertEqual(actual.get_opcodes(),expected.get_opcodes(),(original,current))

    def test_source_reads_cancel_inside_longest_match_without_cache_publication(self):
        original='元'+'文'*450+'甲'+'文'*450+'外';current='文'*450+'乙'+'文'*450+'別'
        token=C._CORRECTION_PATH.set((original,));real=difflib.SequenceMatcher
        phase={'matching':False,'checks':0}
        class ObservedMatcher(real):
            def find_longest_match(self,*args,**kwargs):
                phase['matching']=True
                try:return super().find_longest_match(*args,**kwargs)
                finally:phase['matching']=False
        def cancel():
            if phase['matching']:phase['checks']+=1
            return phase['matching'] and phase['checks']>=8
        try:
            with resource_scope():
                cache,_=retain(C._SourceRangeOpcodes())
                with request_scope(cancel),patch.object(difflib,'SequenceMatcher',ObservedMatcher):
                    with self.assertRaises(SupersededAnalysis):list(C._candidate_source_ranges(current,0,4))
                self.assertEqual(phase['checks'],8)
                self.assertEqual(cache.opcodes,{})
                self.assertTrue(list(C._candidate_source_ranges(current,0,4)))
                self.assertTrue(cache.opcodes)
            self.assertEqual(cache.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

    def test_current_sequence_index_build_can_cancel_before_matching(self):
        original='元資料abc';current='資料abc';checks=[0]
        token=C._CORRECTION_PATH.set((original,))
        def cancel():checks[0]+=1;return checks[0]>=5
        try:
            with resource_scope():
                cache,_=retain(C._SourceRangeOpcodes())
                with request_scope(cancel):
                    with self.assertRaises(SupersededAnalysis):list(C._candidate_source_ranges(current,2,4))
                self.assertEqual(cache.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

    def test_copied_request_does_not_poll_another_threads_owner(self):
        checks=[];results=[];errors=[]
        with request_scope(lambda:checks.append('owner') or False):
            context=contextvars.copy_context()
            def worker():
                try:results.extend(difflib.SequenceMatcher(None,C._SourceRangeText('aaba'),C._SourceRangeText('aba'),autojunk=False).get_opcodes())
                except BaseException as e:errors.append(e)
            t=threading.Thread(target=lambda:context.run(worker));t.start();t.join(5)
            self.assertFalse(t.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(checks,[])
        self.assertEqual(results,difflib.SequenceMatcher(None,'aaba','aba',autojunk=False).get_opcodes())

if __name__=='__main__':unittest.main()
