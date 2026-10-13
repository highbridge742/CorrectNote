# -*- coding: utf-8 -*-
"""Original native pronoun/case/finite proof and the real written gate.

The saved fixture is source-only native IME output from a synthetic reading.
Expected strings are test assertions only, never generation arguments.
"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import corrector as C
import ime_spelling as I
import morphology as M
import reading_segments as R
import semantic_roles as S
from analysis_context import request_scope,SupersededAnalysis
from last_choice import set_active
from tests_analysis_async import initial

SOURCE='どこであるきますか';FACE='どこで歩きますか';RAW='dokodearukimasuka'
class SavedNative:
    def __init__(self,inverse=None):
        fixture=json.loads(Path(__file__).absolute().with_name('tests_native_pronoun_case_fixture.json').read_text(encoding='utf-8'))
        self.first=fixture['conversion'][0]
        self.descriptors=tuple(tuple(row) for row in fixture['conversion'][1])
        self.inverse=(inverse if inverse is not None else fixture['inverse'][0],
                      tuple(tuple(row) for row in fixture['inverse'][1]))
        self.available=True;self.error='';self.conversions=[];self.reversals=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def convert_words(self,source):
        self.conversions.append(source)
        return (self.first,self.descriptors) if source==SOURCE else None
    def reverse_words(self,face):
        self.reversals.append(face)
        return self.inverse if face==self.first else None
    def homophones(self,*args,**kwargs):return ()

@unittest.skipUnless(M.HAS_JANOME,'real native dictionary required')
class NativePronounCaseTests(unittest.TestCase):
    def setUp(self):
        self.state=initial();self.tokenize=C.make_tokenizer(self.state.store)
        self.parts=M.tokenize(SOURCE)
        self.addCleanup(set_active,None)
    def frame(self,parts=None):
        return R.native_reopened_verb_case_faces(SOURCE,self.parts if parts is None else parts,
            2,'で',('どこ',),False)
    def project(self,inverse=None):
        ime=SavedNative(inverse)
        with patch('ime_language.JapaneseIME',return_value=ime):
            value=I.project_first_words(SOURCE,self.state.store,self.state.dict_index,
                self.state.decisions,self.tokenize)
        return value,ime
    def finish(self):
        ime=SavedNative();token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            with patch('ime_language.JapaneseIME',return_value=ime):
                return C._finish_halfwidth_candidate(RAW,0,len(RAW),SOURCE,self.state.store,
                    self.tokenize,self.state.dict_index,self.state.decisions,input_method='romaji')
        finally:C._CORRECTION_INPUT_METHOD.reset(token)

    def test_original_native_pronoun_case_and_finite_witness_own_the_source(self):
        self.assertEqual(self.parts[0].pos_sub,'代名詞:一般')
        self.assertEqual(self.parts[0].surface,self.parts[0].reading)
        self.assertEqual(self.frame(),('どこ',))
        self.assertEqual(R.native_reopened_verb_case_frames(SOURCE),((0,SOURCE,0,2,'で',('どこ',)),))
        self.assertTrue(R.completed_native_reading_clause(SOURCE))
        self.assertTrue(R.completed_native_reading(SOURCE))
        self.assertTrue(C._chunk_is_intact(SOURCE,self.tokenize))
        proof=S.candidate_evidence('どこ','歩き','ますか',before='どこで',case='で')
        self.assertEqual(proof['shared_roles'],['place'])

    def test_missing_actual_pronoun_pos_or_reading_does_not_supply_the_seam(self):
        noun=self.parts[0]
        for pos_sub,reading in (('一般',noun.reading),(noun.pos_sub,'どこう')):
            changed=M.Token(noun.surface,noun.pos,noun.base_form,reading,noun.start,noun.end,
                noun.has_reading,pos_sub,noun.infl_form)
            with self.subTest(pos_sub=pos_sub,reading=reading):
                self.assertEqual(self.frame([changed]+self.parts[1:]),())

    def test_missing_native_pronoun_dictionary_identity_does_not_supply_the_seam(self):
        original=M.dictionary_inflections
        def absent(surface):return () if surface=='どこ' else original(surface)
        with patch.object(M,'dictionary_inflections',side_effect=absent):self.assertEqual(self.frame(),())

    def test_missing_source_finite_witness_does_not_supply_the_seam(self):
        with patch.object(R,'native_case_predicate_witness',return_value=False):self.assertEqual(self.frame(),())

    def test_unknown_argument_roles_and_unfinished_predicates_remain_unproved(self):
        for source in ('なにをよみますか','なにがとどきますか','だれがはしりますか',
                       'どこであるきそう','どこであるき','どこである',
                       'どこであるきそうなんですか','どこであるけないのですか'):
            with self.subTest(source=source):
                self.assertEqual(R.native_reopened_verb_case_frames(source),())
                self.assertFalse(R.completed_native_reading(source))

    def test_one_actual_verb_word_completes_without_forcing_a_changed_noun_pair(self):
        value,ime=self.project()
        self.assertEqual(value,(FACE,((3,6,'歩き'),),True))
        self.assertEqual(ime.conversions,[SOURCE]);self.assertEqual(ime.reversals,[FACE])
        native=SavedNative();parts=M.tokenize(native.first)
        self.assertIsNone(I._first_case_word_proposal(SOURCE,native.first,native.descriptors,
            parts,self.parts,I.native_spelling_boundaries(SOURCE,parts),self.state.decisions))

    def test_missing_actual_written_meaning_cannot_use_the_positive_source_frame(self):
        original=S.candidate_evidence
        def unknown(noun,head,*args,**kwargs):
            return None if (noun,head)==('どこ','歩き') else original(noun,head,*args,**kwargs)
        with patch.object(S,'candidate_evidence',side_effect=unknown):
            self.assertEqual(self.frame(),('どこ',))
            value,_=self.project();self.assertNotEqual(value and value[0],FACE)
            self.assertNotEqual(self.finish(),FACE)

    def test_explicit_head_choice_conflict_cannot_cut_the_source_owner(self):
        self.state.choices.remember('あるき','行き')
        self.assertFalse(R.native_reopened_verb_spelling_boundary(SOURCE,3,6,'歩き'))
        value,_=self.project();self.assertNotEqual(value and value[0],FACE)
        self.assertNotEqual(self.finish(),FACE)

    def test_explicit_whole_owner_choice_cannot_be_cut_for_a_shorter_word(self):
        self.state.choices.remember('であるき','出歩き')
        self.assertFalse(R.native_reopened_verb_spelling_boundary(SOURCE,3,6,'歩き'))
        value,_=self.project();self.assertNotEqual(value and value[0],FACE)
        self.assertNotEqual(self.finish(),FACE)

    def test_actual_head_choice_retains_the_positive_boundary(self):
        self.state.choices.remember('あるき','歩き')
        self.assertTrue(R.native_reopened_verb_spelling_boundary(SOURCE,3,6,'歩き'))
        self.assertEqual(self.finish(),FACE)

    def test_word_and_cross_seam_blocks_reach_the_common_gate(self):
        from decisions import DecisionStore
        for protected in ('あるき','こであるき'):
            self.state.decisions=DecisionStore();self.state.decisions.protect(protected)
            with self.subTest(protected=protected):self.assertNotEqual(self.finish(),FACE)
        self.state.decisions=DecisionStore();self.state.decisions.reject('あるき','歩き')
        self.assertNotEqual(self.finish(),FACE)

    def test_same_original_kana_and_ascii_common_gates_are_retained(self):
        original=C._check_replacement;seen=[]
        def checked(line,edit,*args,**kwargs):
            value=original(line,edit,*args,**kwargs);seen.append((line,edit,value));return value
        with patch.object(C,'_check_replacement',side_effect=checked):self.assertEqual(self.finish(),FACE)
        self.assertTrue(any(line==SOURCE and edit[:3]==(0,len(SOURCE),FACE) and value[0] is not None
                            for line,edit,value in seen))
        self.assertEqual(seen[-1][0],RAW)
        self.assertEqual(seen[-1][1][:3],(0,len(RAW),FACE))
        self.assertIsNotNone(seen[-1][2][0])

    def test_full_gate_rejection_or_range_change_cannot_publish_the_written_field(self):
        original=C._check_replacement
        for target,mode in (('kana','reject'),('ascii','reject'),('ascii','shift')):
            def checked(line,edit,*args,**kwargs):
                if edit[2]==FACE and line==(SOURCE if target=='kana' else RAW):
                    return ((1,edit[1],edit[2],edit[3]),'shift') if mode=='shift' else (None,'independent_refusal')
                return original(line,edit,*args,**kwargs)
            with self.subTest(target=target,mode=mode),patch.object(C,'_check_replacement',side_effect=checked):
                self.assertNotEqual(self.finish(),FACE)

    def test_source_finite_witness_accept_and_reject_check_cancellation(self):
        original=R.native_case_predicate_witness
        for rejected in (False,True):
            stale=False
            def checked(*args,**kwargs):
                nonlocal stale
                value=original(*args,**kwargs);stale=True;return False if rejected else value
            with self.subTest(rejected=rejected),request_scope(lambda:stale),patch.object(R,'native_case_predicate_witness',side_effect=checked):
                with self.assertRaises(SupersededAnalysis):self.frame()

    def test_original_ascii_gate_accept_and_reject_check_cancellation(self):
        original=C._check_replacement
        for rejected in (False,True):
            stale=False
            def checked(line,edit,*args,**kwargs):
                nonlocal stale
                value=original(line,edit,*args,**kwargs)
                if line==RAW and edit[2]==FACE:
                    stale=True
                    if rejected:value=(None,'independent_refusal')
                return value
            with self.subTest(rejected=rejected),request_scope(lambda:stale),patch.object(C,'_check_replacement',side_effect=checked):
                with self.assertRaises(SupersededAnalysis):self.finish()

if __name__=='__main__':unittest.main()
