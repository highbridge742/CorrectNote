import unittest
from unittest.mock import patch
import corrector as C,halfwidth

class ExistingNextGate(Exception):pass

class OriginalLinkScopeTests(unittest.TestCase):
    def test_missing_scheme_inside_original_link_rejects_without_borrowing_other_field(self):
        ancestor='しょるい\t👩🏽‍💻 https://x.test/資料abc\tabc'
        current='書類\t👩🏽‍💻 資料abc\tabc'
        token=C._CORRECTION_PATH.set((ancestor,))
        try:
            inner=current.index('abc')+1;outer=current.rindex('abc')+1
            mapped=list(C._candidate_source_ranges(current,inner,inner,allow_empty=True))
            point=ancestor.index('abc')+1
            self.assertIn((ancestor,point,point),mapped)
            with patch.object(halfwidth,'original_ascii_expression',return_value=True):
                self.assertEqual(C._check_replacement(current,(inner,inner,'X','かな入力'),None,None),(None,'original_explicit_link'))
                self.assertEqual(C._check_replacement(current,(outer,outer,'X','かな入力'),None,None),(None,'original_ascii_expression'))
            # The deleted URL scheme meets two original boundaries; do not guess.
            ambiguous=current.index('資料')
            self.assertEqual(list(C._candidate_source_ranges(current,ambiguous,ambiguous,allow_empty=True)),[(current,ambiguous,ambiguous)])
            with patch.object(halfwidth,'original_ascii_expression',return_value=True):
                for edge in (ambiguous,current.index('abc')+len('abc')):
                    self.assertEqual(C._check_replacement(current,(edge,edge,'X','かな入力'),None,None),(None,'original_ascii_expression'))
        finally:C._CORRECTION_PATH.reset(token)


    def test_existing_ascii_gate_receives_only_its_legacy_nonempty_ancestor_views(self):
        ancestor='C:\\資料abc\t外';short='cc\\資料abc\t外';long=short+'extra'
        cases=((short,9,10,[(short,9,10),(ancestor,9,10)]),
               (short,10,10,[(short,10,10)]),(long,10,15,[(long,10,15)]))
        for current,start,end,expected in cases:
            token=C._CORRECTION_PATH.set((ancestor,));calls=[];mapper=C._candidate_source_ranges
            try:
                def ascii_gate(source,a,b):calls.append((source,a,b));return False
                with patch.object(C,'_candidate_source_ranges',wraps=mapper) as mapped,patch.object(halfwidth,'original_ascii_expression',side_effect=ascii_gate),patch('romaji_source.candidate_evidence',side_effect=ExistingNextGate):
                    with self.assertRaises(ExistingNextGate):C._check_replacement(current,(start,end,'Z','かな入力'),None,None)
                self.assertEqual(calls,expected);self.assertEqual(mapped.call_count,1)
            finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
