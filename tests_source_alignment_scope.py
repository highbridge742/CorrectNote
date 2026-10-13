import difflib,unittest
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import corrector as C
from ime_session import resource_scope,retain
from analysis_context import request_scope,SupersededAnalysis


def frozen93_ranges(line,start,end,allow_empty=False):
    """Frozen pre-cache mapping as an independent equivalence oracle."""
    yield line,start,end
    for ancestor in C._CORRECTION_PATH.get():
        if ancestor==line:continue
        opcodes=difflib.SequenceMatcher(None,ancestor,line,autojunk=False).get_opcodes()
        def boundary(position):
            points=set()
            for tag,a,b,c,d in opcodes:
                if tag=='equal' and c<=position<=d:points.add(a+position-c)
                elif tag!='equal':
                    if position==c:points.add(a)
                    if position==d:points.add(b)
            return next(iter(points)) if len(points)==1 else None
        a,b=boundary(start),boundary(end)
        if a is not None and b is not None and (a<b or allow_empty and a==b):
            yield ancestor,a,b


class SourceAlignmentScopeTests(unittest.TestCase):
    def test_all_398_intervals_keep_order_and_ambiguous_boundaries(self):
        checks=0
        for ancestor,current in (
                ('C:\\資料abc','資料abc'),('C:\\資料abc','??\\資料abc'),
                ('C:\\xyz','資料abc'),('💡 C:\\資料abc\tabc','💡 cc\\資料abc\tabc'),
                ('C:\\資料abc\t外','cc\\資料abc\t外extra'),('C:\\aaabaaa','cc\\aabaaa')):
            token=C._CORRECTION_PATH.set((current,ancestor))
            try:
                with resource_scope():
                    for start in range(len(current)+1):
                        for end in range(start,len(current)+1):
                            for empty in (False,True):
                                self.assertEqual(list(C._candidate_source_ranges(current,start,end,allow_empty=empty)),
                                                 list(frozen93_ranges(current,start,end,empty)),
                                                 (ancestor,current,start,end,empty))
                            checks+=1
            finally:C._CORRECTION_PATH.reset(token)
        self.assertEqual(checks,398)

    def test_one_request_reuses_immutable_opcodes_then_clears_all_keys(self):
        ancestor='C:\\資料abc';current='資料abc'
        token=C._CORRECTION_PATH.set((ancestor,))
        try:
            with patch.object(difflib,'SequenceMatcher',wraps=difflib.SequenceMatcher) as matcher:
                with resource_scope():
                    expected=list(C._candidate_source_ranges(current,2,4))
                    cache,_=retain(C._SourceRangeOpcodes())
                    with resource_scope():
                        self.assertEqual(list(C._candidate_source_ranges(current,2,4)),expected)
                        list(C._candidate_source_ranges(current,3,3,allow_empty=True))
                    self.assertEqual(matcher.call_count,1)
                    values=list(cache.opcodes.values())
                    self.assertTrue(values)
                    self.assertTrue(all(isinstance(rows,tuple) and all(isinstance(row,tuple) for row in rows) for rows in values))
                self.assertEqual(cache.opcodes,{})
                with resource_scope():self.assertEqual(list(C._candidate_source_ranges(current,2,4)),expected)
                self.assertEqual(matcher.call_count,2)
        finally:C._CORRECTION_PATH.reset(token)

    def test_cancelled_cold_alignment_is_not_cached_and_warm_hit_is_checked(self):
        ancestor='C:\\資料abc';current='資料abc';stale=[False]
        token=C._CORRECTION_PATH.set((ancestor,));real=difflib.SequenceMatcher
        class CancelAtResult:
            def __init__(self,*args,**kwargs):self.inner=real(*args,**kwargs)
            def get_opcodes(self):
                result=self.inner.get_opcodes();stale[0]=True;return result
        try:
            with resource_scope():
                cache,_=retain(C._SourceRangeOpcodes())
                with request_scope(lambda:stale[0]),patch.object(difflib,'SequenceMatcher',new=CancelAtResult):
                    with self.assertRaises(SupersededAnalysis):list(C._candidate_source_ranges(current,2,4))
                self.assertEqual(cache.opcodes,{})
                stale[0]=False
                self.assertTrue(list(C._candidate_source_ranges(current,2,4)))
                calls=[0]
                def cancel_warm_publication():
                    calls[0]+=1;return calls[0]>=3
                with request_scope(cancel_warm_publication):
                    with self.assertRaises(SupersededAnalysis):list(C._candidate_source_ranges(current,2,4))
            self.assertEqual(cache.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

    def test_failed_alignment_retries_and_does_not_publish_partial_data(self):
        token=C._CORRECTION_PATH.set(('C:\\資料abc',))
        try:
            with resource_scope():
                cache,_=retain(C._SourceRangeOpcodes())
                with patch.object(difflib,'SequenceMatcher',side_effect=ValueError('synthetic alignment failure')):
                    with self.assertRaisesRegex(ValueError,'synthetic'):list(C._candidate_source_ranges('資料abc',2,4))
                self.assertEqual(cache.opcodes,{})
                self.assertEqual(list(C._candidate_source_ranges('資料abc',2,4)),
                                 [('資料abc',2,4),('C:\\資料abc',5,7)])
            self.assertEqual(cache.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

    def test_context_copied_to_another_thread_does_not_borrow_owner_cache(self):
        current='資料abc';token=C._CORRECTION_PATH.set(('C:\\資料abc',))
        def query():return list(C._candidate_source_ranges(current,2,4))
        try:
            with resource_scope(),patch.object(difflib,'SequenceMatcher',wraps=difflib.SequenceMatcher) as matcher:
                expected=query();ctx=copy_context()
                with ThreadPoolExecutor(max_workers=1) as pool:self.assertEqual(pool.submit(ctx.run,query).result(timeout=5),expected)
                self.assertEqual(query(),expected)
                self.assertEqual(matcher.call_count,2)
            with patch.object(difflib,'SequenceMatcher',wraps=difflib.SequenceMatcher) as matcher:
                self.assertEqual(query(),expected);self.assertEqual(query(),expected)
                self.assertEqual(matcher.call_count,2)
        finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
