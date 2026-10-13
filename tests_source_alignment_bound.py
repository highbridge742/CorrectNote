# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""A globally absent edge cannot participate in any exact match."""
import difflib,itertools,random,unittest
from unittest.mock import patch
import corrector as C
from analysis_context import request_scope,SupersededAnalysis
from ime_session import resource_scope,retain
from tests_source_alignment_scope import frozen93_ranges

class BoundedAlignmentTests(unittest.TestCase):
    def compare(self,original,current):
        real=difflib.SequenceMatcher;seen=[]
        def observe(*args,**kwargs):
            obj=real(*args,**kwargs);seen.append(obj);return obj
        token=C._CORRECTION_PATH.set((original,))
        try:
            with patch.object(difflib,'SequenceMatcher',side_effect=observe):
                list(C._candidate_source_ranges(current,0,len(current),allow_empty=True))
            if original==current:self.assertEqual(seen,[]);return
            self.assertEqual(len(seen),1)
            std=real(None,original,current,autojunk=False)
            self.assertEqual(seen[0].get_matching_blocks(),std.get_matching_blocks(),(original,current))
            self.assertEqual(seen[0].get_opcodes(),std.get_opcodes(),(original,current))
            proof=C._source_range_bounded_match(original,current)
            if proof is not None:
                a,b,n=proof
                self.assertEqual(std.get_matching_blocks(),[difflib.Match(a,b,n),difflib.Match(len(original),len(current),0)])
                unused_a=original[:a]+original[a+n:]
                unused_b=current[:b]+current[b+n:]
                self.assertTrue(not set(unused_a)&set(current) or not set(unused_b)&set(original))
        finally:C._CORRECTION_PATH.reset(token)

    def test_three_character_exhaustion_keeps_opcodes_and_tie_order(self):
        values=[''.join(chars) for n in range(5) for chars in itertools.product('abc',repeat=n)]
        for original in values:
            for current in values:self.compare(original,current)

    def test_new_unicode_random_and_repeated_or_noncontained_inputs(self):
        rng=random.Random(113);alphabet='ab甲乙💡\u0301\t⇒'
        for _ in range(500):
            original=''.join(rng.choice(alphabet) for _ in range(rng.randrange(25)))
            current=''.join(rng.choice(alphabet) for _ in range(rng.randrange(25)))
            self.compare(original,current)
        word='文'*200+'💡é\t資料⇒'
        for original,current in ((word+'末', '先'+word),('先'+word+'末',word+'外'),
                ('未'+word+'末',word+'間'+word+'外'),(word+'間'+word+'外','未'+word+'末'),
                ('aaXbb','aaYbb'),('ababxaba','abaxabab'),('aab','baa'),('aaaXaaa','aaaYaaa')):
            self.compare(original,current)

    def test_bounded_fast_path_and_shared_interior_gap_fallback(self):
        real=difflib.SequenceMatcher
        class NoLongest(real):
            def find_longest_match(self,*args,**kwargs):raise AssertionError('standard required')
        for original,current in (('元'+'文'*900+'外','文'*900+'別'),('文'*900+'別','元'+'文'*900+'外')):
            token=C._CORRECTION_PATH.set((original,))
            try:
                expected=list(frozen93_ranges(current,0,4))
                with patch.object(difflib,'SequenceMatcher',NoLongest):
                    self.assertEqual(list(C._candidate_source_ranges(current,0,4)),expected)
            finally:C._CORRECTION_PATH.reset(token)
        token=C._CORRECTION_PATH.set(('元'+'文'*450+'甲'+'文'*450+'外',))
        try:
            with patch.object(difflib,'SequenceMatcher',NoLongest):
                with self.assertRaisesRegex(AssertionError,'standard required'):
                    list(C._candidate_source_ranges('文'*450+'乙'+'文'*450+'別',0,4))
        finally:C._CORRECTION_PATH.reset(token)

    def test_cancel_at_bounded_find_return_cannot_publish_cache(self):
        stale=[False];calls=[]
        class Current(str):
            def find(self,needle,*args):
                result=super().find(needle,*args);calls.append((needle,result))
                if needle=='文'*100:stale[0]=True
                return result
        original='元'+'文'*100+'外';current=Current('文'*100+'別')
        token=C._CORRECTION_PATH.set((original,))
        try:
            with resource_scope():
                cache,_=retain(C._SourceRangeOpcodes())
                with request_scope(lambda:stale[0],poll_interval=3600):
                    with self.assertRaises(SupersededAnalysis):list(C._candidate_source_ranges(current,0,4))
                self.assertEqual(cache.opcodes,{})
            self.assertEqual(cache.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
