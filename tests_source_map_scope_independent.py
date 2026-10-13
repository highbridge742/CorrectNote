# -*- coding: utf-8 -*-
import unittest,contextvars,threading,difflib
from unittest.mock import patch
import corrector as C
from ime_session import resource_scope,retain

class SourceMapScopeTests(unittest.TestCase):
    def test_suspended_generator_reenters_current_scope_without_repopulating_closed_cache(self):
        original='資料 abc\t外';other='資材 abc\t外';line='資料 xabc\t外'
        token=C._CORRECTION_PATH.set((original,other))
        try:
            with resource_scope():
                views=C._candidate_source_ranges(line,4,7)
                next(views);self.assertEqual(next(views),(original,3,6))
                closed,_=retain(C._SourceRangeOpcodes());self.assertEqual(len(closed.opcodes),1)
            self.assertEqual(closed.opcodes,{})
            with resource_scope():
                fresh,_=retain(C._SourceRangeOpcodes())
                self.assertEqual(next(views),(other,3,6))
                self.assertEqual(closed.opcodes,{})
                self.assertEqual(len(fresh.opcodes),1)
            self.assertEqual(fresh.opcodes,{})
            views.close()
        finally:C._CORRECTION_PATH.reset(token)

    def test_partly_consumed_generator_does_not_keep_alignment_after_scope_closes(self):
        original='資料 abc\t外';line='資料 xabc\t外'
        token=C._CORRECTION_PATH.set((original,))
        try:
            with resource_scope():
                views=C._candidate_source_ranges(line,4,7)
                self.assertEqual(next(views),(line,4,7))
                self.assertEqual(next(views),(original,3,6))
                cache,shared=retain(C._SourceRangeOpcodes());self.assertTrue(shared)
                self.assertEqual(len(cache.opcodes),1)
                views.close()
                self.assertEqual(len(cache.opcodes),1)
            self.assertEqual(cache.opcodes,{})
            with resource_scope():
                other,shared=retain(C._SourceRangeOpcodes());self.assertIsNot(other,cache)
                self.assertEqual(other.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

    def test_copied_context_on_another_thread_cannot_borrow_parent_alignment(self):
        original='資料 abc\t外';line='資料 xabc\t外';native=difflib.SequenceMatcher
        token=C._CORRECTION_PATH.set((original,));results=[];errors=[]
        try:
            with resource_scope():
                parent=list(C._candidate_source_ranges(line,4,7))
                cache,_=retain(C._SourceRangeOpcodes());context=contextvars.copy_context()
                def work():
                    try:
                        with patch.object(difflib,'SequenceMatcher',wraps=native) as matcher:
                            results.append(list(C._candidate_source_ranges(line,4,7)))
                            results.append(list(C._candidate_source_ranges(line,4,7)))
                            results.append(matcher.call_count)
                    except BaseException as error:errors.append(error)
                thread=threading.Thread(target=lambda:context.run(work));thread.start();thread.join(10)
                self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
                self.assertEqual(results,[parent,parent,2]);self.assertEqual(len(cache.opcodes),1)
            self.assertEqual(cache.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
