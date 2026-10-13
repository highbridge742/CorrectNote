# -*- coding: utf-8 -*-
"""Earlier original words survive a same-field pair's shortening."""
import json,unittest
from pathlib import Path
from unittest.mock import patch
from tests_analysis_async import initial
from analysis_context import request_scope,SupersededAnalysis
from last_choice import set_active
import corrector as C,ime_spelling as I,morphology as M

SOURCE='わたしはこうえんであるきそうです'
FACE='私は公園で歩きそうです'
RAW='watashihakouendearukisoudesu'

class PrefixIME:
    def __init__(self,source=SOURCE):
        record=json.loads(Path(__file__).with_name('tests_ime_pair_prefix_native.json').read_text(encoding='utf8'))[source]
        value=record['conversion'];self.source=source;self.face=value[0]
        self.descriptors=tuple(map(tuple,value[1]));self.inverse=(record['inverse'][0],tuple(map(tuple,record['inverse'][1])))
        self.available=True;self.error=''
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def convert_words(self,reading):return (self.face,self.descriptors) if reading==self.source else None
    def reverse_words(self,text):return self.inverse if text==self.face else None
    def homophones(self,*args,**kwargs):return ()

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class PairPrefixContracts(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.fn=C.make_tokenizer(self.a.store);self.addCleanup(set_active,None)
    def project(self,source=SOURCE):
        with patch('ime_language.JapaneseIME',return_value=PrefixIME(source)):
            return I.project_first_words(source,self.a.store,self.a.dict_index,self.a.decisions,self.fn)
    def finish(self,line=RAW,start=0,end=None):
        end=len(line) if end is None else end
        from halfwidth import romaji_to_kana
        fixed=romaji_to_kana(line[start:end])[0]
        token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            with patch('ime_language.JapaneseIME',return_value=PrefixIME(fixed)):
                return C._finish_halfwidth_candidate(line,start,end,fixed,self.a.store,self.fn,self.a.dict_index,self.a.decisions,input_method='romaji')
        finally:C._CORRECTION_INPUT_METHOD.reset(token)
    def test_earlier_subject_preserved_and_original_edits_are_sorted(self):
        from contextual_repair import _apply
        value=self.project()
        self.assertEqual(value,(FACE,((0,3,'私'),(4,8,'公園'),(9,12,'歩き')),True))
        self.assertEqual(_apply(SOURCE,value[1]),FACE)
        for source,expected in (('わたしはこうえんであるきます','私は公園で歩きます'),
                                ('わたしはこうえんであるきそうですか','私は公園で歩きそうですか')):
            with self.subTest(source=source):self.assertEqual(self.project(source)[0],expected)
    def test_source_prefix_common_gate_is_still_independent(self):
        original=C._check_replacement;seen=[]
        def check(text,replacement,*args,**kwargs):
            seen.append((text,replacement[:3]))
            if replacement[:3]==(0,3,'私'):return None,'independent_prefix_refusal'
            return original(text,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=check):value=self.project()
        self.assertEqual(value[0],'わたしは公園で歩きそうです')
        self.assertIn(('わたしは公園で歩きそうです',(0,3,'私')),seen)
    def test_prefix_protect_is_preserved_by_the_original_whole_field_gate(self):
        self.a.decisions.protect('わたし')
        original=C._check_replacement;seen=[]
        def check(text,replacement,*args,**kwargs):
            value=original(text,replacement,*args,**kwargs)
            if replacement[:3]==(0,len(SOURCE),'わたしは公園で歩きそうです'):
                seen.append(value)
            return value
        with patch.object(C,'_check_replacement',side_effect=check):value=self.project()
        self.assertIsNone(value)
        self.assertTrue(seen);self.assertIsNone(seen[0][0])
    def test_original_ascii_final_gate_still_owns_the_whole_field(self):
        original=C._check_replacement;seen=[]
        def check(text,replacement,*args,**kwargs):
            seen.append((text,replacement[:3]));return original(text,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=check):self.assertEqual(self.finish(),FACE)
        self.assertEqual(seen[-1],(RAW,(0,len(RAW),FACE)))
        for shift,refuse in ((False,True),(True,False)):
            def blocked(text,replacement,*args,**kwargs):
                if text==RAW and replacement[2]==FACE:
                    return (None,'original_refusal') if refuse else ((1,len(RAW),FACE,'IT・PC操作'),'shifted')
                return original(text,replacement,*args,**kwargs)
            with self.subTest(shift=shift),patch.object(C,'_check_replacement',side_effect=blocked):self.assertNotEqual(self.finish(),FACE)
    def test_actual_outer_field_keeps_ascii_protection_and_other_field(self):
        line='未変更\t'+RAW;start=line.index(RAW)
        self.assertEqual(self.finish(line,start,len(line)),FACE)
        self.a.decisions.protect(RAW)
        self.assertIsNone(self.finish(line,start,len(line)))
    def test_cancel_after_prefix_or_original_ascii_gate_unwinds(self):
        original=C._check_replacement
        for target in ('prefix','ascii'):
            for reject in (False,True):
                pending=[False]
                def check(text,replacement,*args,**kwargs):
                    value=original(text,replacement,*args,**kwargs)
                    if (target=='prefix' and replacement[:3]==(0,3,'私') or target=='ascii' and text==RAW and replacement[2]==FACE):
                        pending[0]=True
                        if reject:return None,'independent_cancel_refusal'
                    return value
                with self.subTest(target=target,reject=reject),request_scope(lambda:pending[0],poll_interval=0),patch.object(C,'_check_replacement',side_effect=check):
                    with self.assertRaises(SupersededAnalysis):self.finish()
    def test_actual_code_and_incomplete_function_chain_remain_unconverted(self):
        import app
        for line in ('print('+RAW+')','x='+RAW,'https://example.test/'+RAW,RAW+'_value'):
            with self.subTest(line=line):
                row=app.correct_line(line,self.a.store,input_method='romaji',dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None)
                self.assertEqual(row['corrected'],line)
        value=self.project('わたしはこうえんでであるきます')
        self.assertNotEqual(value and value[0],'私は公園で歩きます')

if __name__=='__main__':unittest.main()
