# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""A real different written verb cannot borrow another verb's noun role."""
import json,unittest
from pathlib import Path
from unittest.mock import patch
from tests_analysis_async import initial
from last_choice import set_active
import corrector as C,ime_spelling as I,morphology as M,reading_segments as R,semantic_roles as S

class ActualWrittenNative:
    def __init__(self,record,fixture):
        self.source=fixture['source'];self.face=record['written']
        self.descriptors=tuple(map(tuple,fixture['descriptors']))
        self.inverse=(record['inverse'][0],tuple(map(tuple,record['inverse'][1])))
        self.available=True;self.error=''
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def convert_words(self,source):
        return (self.face,self.descriptors) if source==self.source else None
    def reverse_words(self,surface):return self.inverse if surface==self.face else None
    def homophones(self,*args,**kwargs):return ()

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class NativePronounWrittenTests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads(Path(__file__).with_name('tests_native_pronoun_written_fixture.json').read_text(encoding='utf8'))
        self.records={r['face']:r for r in self.fixture['records']}
        self.a=initial();self.fn=C.make_tokenizer(self.a.store)
        self.addCleanup(set_active,None)
    def test_actual_different_written_head_owns_its_meaning(self):
        self.assertTrue(self.fixture['source_only_capture'])
        self.assertTrue(R.completed_native_reading(self.fixture['source']))
        parts=[]
        for face in ('行き','生き'):
            record=self.records[face]
            self.assertEqual(record['inverse'][0],self.fixture['source'])
            self.assertTrue(any(pos.startswith('動詞,自立,') and rd=='いき' and form=='連用形'
                                for pos,form,base,rd in M.dictionary_inflections(face)))
            head=next(t for t in M.tokenize(record['written']) if t.surface==face)
            parts.append((head.reading,head.pos,head.pos_sub,head.infl_form))
        self.assertEqual(parts[0],parts[1])
        accepted=S.candidate_evidence('どこ','行き','ますか',before='どこへ',case='へ')
        other=S.candidate_evidence('どこ','生き','ますか',before='どこへ',case='へ')
        self.assertEqual(accepted['shared_roles'],['place'])
        self.assertFalse(other and other['shared_roles'])
    def test_same_reading_source_cannot_complete_a_different_written_meaning(self):
        values={}
        for face in ('行き','生き'):
            record=self.records[face]
            with patch('ime_language.JapaneseIME',return_value=ActualWrittenNative(record,self.fixture)):
                values[face]=I.project_first_words(self.fixture['source'],self.a.store,self.a.dict_index,self.a.decisions,self.fn)
        self.assertEqual(values['行き'][0],self.records['行き']['written'])
        self.assertNotEqual(values['生き'] and values['生き'][0],self.records['生き']['written'])
    def test_original_ascii_completion_keeps_the_actual_written_meaning(self):
        raw='dokoheikimasuka';values={};token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            for face in ('行き','生き'):
                with patch('ime_language.JapaneseIME',return_value=ActualWrittenNative(self.records[face],self.fixture)):
                    values[face]=C._finish_halfwidth_candidate(raw,0,len(raw),self.fixture['source'],
                        self.a.store,self.fn,self.a.dict_index,self.a.decisions,input_method='romaji')
        finally:C._CORRECTION_INPUT_METHOD.reset(token)
        self.assertEqual(values['行き'],self.records['行き']['written'])
        self.assertNotEqual(values['生き'],self.records['生き']['written'])
if __name__=='__main__':unittest.main()
