# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
import difflib,itertools,unittest
from unittest.mock import patch
import corrector as C
from tests_source_alignment_scope import frozen93_ranges


class ExactContainmentTests(unittest.TestCase):
    def test_exhaustive_binary_sequences_preserve_actual_opcodes(self):
        values=[''.join(chars) for n in range(6) for chars in itertools.product('ab',repeat=n)]
        real=difflib.SequenceMatcher;seen=[]
        def observe(*args,**kwargs):
            matcher=real(*args,**kwargs);seen.append(matcher);return matcher
        for original in values:
            token=C._CORRECTION_PATH.set((original,))
            try:
                for current in values:
                    seen.clear()
                    with patch.object(difflib,'SequenceMatcher',side_effect=observe):
                        list(C._candidate_source_ranges(current,0,len(current),allow_empty=True))
                    if original==current:self.assertEqual(seen,[])
                    else:
                        self.assertEqual(len(seen),1)
                        self.assertEqual(seen[0].get_opcodes(),real(None,original,current,autojunk=False).get_opcodes(),(original,current))
            finally:C._CORRECTION_PATH.reset(token)

    def test_unicode_containment_repeated_occurrences_and_all_edges(self):
        for original,current in (
                ('ab','acab'),('acab','ab'),('ab','abab'),('abab','ab'),
                ('資料','前資料資料後'),('前資料資料後','資料'),
                ('💡e\u0301','先💡e\u0301\t後'),('先💡e\u0301\t後','💡e\u0301'),
                ('資料\t⇒外','C:\\資料\t⇒外suffix'),('x資料\t⇒外','資料\t⇒外x')):
            token=C._CORRECTION_PATH.set((original,))
            try:
                for start in range(len(current)+1):
                    for end in range(start,len(current)+1):
                        for empty in (False,True):
                            self.assertEqual(list(C._candidate_source_ranges(current,start,end,allow_empty=empty)),list(frozen93_ranges(current,start,end,empty)),(original,current,start,end,empty))
            finally:C._CORRECTION_PATH.reset(token)

    def test_only_whole_containment_skips_longest_match_computation(self):
        real=difflib.SequenceMatcher
        class NoLongest(real):
            def find_longest_match(self,*args,**kwargs):raise AssertionError('unproved alignment')
        for original,current in (('文'*900,'元'+'文'*900+'後'),('元'+'文'*900+'後','文'*900)):
            token=C._CORRECTION_PATH.set((original,))
            try:
                with patch.object(difflib,'SequenceMatcher',NoLongest):self.assertTrue(list(C._candidate_source_ranges(current,0,len(current))))
            finally:C._CORRECTION_PATH.reset(token)
        token=C._CORRECTION_PATH.set(('元'+'文'*450+'甲'+'文'*450+'外',))
        try:
            with patch.object(difflib,'SequenceMatcher',NoLongest):
                with self.assertRaisesRegex(AssertionError,'unproved'):list(C._candidate_source_ranges('文'*450+'乙'+'文'*450+'別',0,4))
        finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
