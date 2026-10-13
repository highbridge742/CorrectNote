# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Original native words supply proof before the combined common gate."""
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

SOURCE='こうえんであるきそうです'
FACE='公園で歩きそうです'
RAW='kouendearukisoudesu'

class SavedIME:
    def __init__(self,source,face=None,inverse=None):
        fixtures=json.loads(Path(__file__).with_name('tests_ime_first_case_native_fixtures.json').read_text(encoding='utf-8'))
        record=fixtures[source]
        conversion=record['conversion'];self.source=source
        self.face=face if face is not None else conversion[0]
        self.descriptors=tuple(tuple(row) for row in conversion[1])
        self.inverse=(inverse if inverse is not None else record['inverse'][0],
                      tuple(tuple(row) for row in record['inverse'][1]))
        self.available=True;self.error='';self.conversions=[];self.reversals=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def convert_words(self,reading):
        self.conversions.append(reading)
        return (self.face,self.descriptors) if reading==self.source else None
    def reverse_words(self,text):
        self.reversals.append(text)
        return self.inverse if text==self.face else None
    def homophones(self,*args,**kwargs):return ()

@unittest.skipUnless(M.HAS_JANOME,'real native dictionary required')
class FirstCaseProjectionContracts(unittest.TestCase):
    def setUp(self):
        self.state=initial();self.tokenize=C.make_tokenizer(self.state.store)
        self.addCleanup(set_active,None)

    def project(self,source=SOURCE,face=None,module=I,inverse=None):
        ime=SavedIME(source,face=face,inverse=inverse)
        with patch('ime_language.JapaneseIME',return_value=ime):
            value=module.project_first_words(source,self.state.store,self.state.dict_index,
                self.state.decisions,self.tokenize)
        return value,ime

    def construction(self,source=SOURCE,face=None):
        ime=SavedIME(source,face=face);parts=M.tokenize(ime.face)
        bounds=I.native_spelling_boundaries(source,parts)
        return I._first_case_word_proposal(source,ime.face,ime.descriptors,parts,M.tokenize(source),bounds,self.state.decisions)

    def finish(self,raw=RAW):
        from halfwidth import romaji_to_kana
        ime=SavedIME(romaji_to_kana(raw)[0])
        token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            with patch('ime_language.JapaneseIME',return_value=ime):
                return C._finish_halfwidth_candidate(raw,0,len(raw),romaji_to_kana(raw)[0],
                    self.state.store,self.tokenize,self.state.dict_index,self.state.decisions,input_method='romaji')
        finally:C._CORRECTION_INPUT_METHOD.reset(token)

    def test_combined_candidate_is_the_first_common_gate(self):
        original=C._check_replacement;seen=[]
        def check(line,replacement,*args,**kwargs):
            seen.append((line,replacement))
            if replacement[:3]==(0,4,'公園'):raise AssertionError('intermediate nominal C was attempted')
            return original(line,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=check):value,ime=self.project()
        self.assertEqual(value,(FACE,((0,4,'公園'),(5,8,'歩き')),True))
        self.assertEqual(seen[0],(SOURCE,(0,len(SOURCE),FACE,'かな入力')))
        self.assertEqual(ime.conversions,[SOURCE]);self.assertEqual(ime.reversals,[FACE])

    def test_proof_binds_original_native_and_actual_written_positions(self):
        projected,edits,proof=self.construction()
        self.assertEqual(projected,FACE);self.assertEqual(edits,((0,4,'公園'),(5,8,'歩き')))
        self.assertEqual(proof['field'],(0,12));self.assertEqual(proof['noun_source'],(0,4))
        self.assertEqual(proof['noun_candidate'],(0,2));self.assertEqual(proof['case_source'],(4,5))
        self.assertEqual(proof['case_candidate'],(2,3));self.assertEqual(proof['predicate_source'],(5,8))
        self.assertEqual(proof['predicate_candidate'],(3,5));self.assertEqual(proof['predicate_face'],'歩き')
        self.assertTrue(proof['source_fit']);self.assertEqual(proof['actual_fit']['shared_roles'],['place'])

    def test_completed_question_and_hearsay_keep_source_grammar(self):
        for source,expected in (('こうえんであるきそうですか','公園で歩きそうですか'),
                                ('こうえんであるくそうです','公園で歩くそうです')):
            with self.subTest(source=source):
                value,_=self.project(source);self.assertEqual(value[0],expected)

    def test_combined_gate_range_change_cannot_publish_the_full_candidate(self):
        original=C._check_replacement
        def shifted(line,replacement,*args,**kwargs):
            if replacement[:3]==(0,len(SOURCE),FACE):return (1,len(SOURCE),FACE,'かな入力'),'shifted'
            return original(line,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=shifted):value,_=self.project()
        self.assertNotEqual(value and value[0],FACE)

    def test_original_ascii_completion_keeps_both_original_common_gates(self):
        original=C._check_replacement;seen=[]
        def checked(line,replacement,*args,**kwargs):
            result=original(line,replacement,*args,**kwargs);seen.append((line,replacement,result))
            return result
        with patch.object(C,'_check_replacement',side_effect=checked):value=self.finish()
        self.assertEqual(value,FACE)
        self.assertIn((SOURCE,(0,len(SOURCE),FACE,'かな入力'),(seen[-2][2][0],'accepted')),seen)
        self.assertEqual(seen[-1][0],RAW);self.assertEqual(seen[-1][1][:3],(0,len(RAW),FACE))
        self.assertIsNotNone(seen[-1][2][0])

    def test_outer_original_kana_and_ascii_refusals_are_not_rescued(self):
        original=C._check_replacement
        for target in ('kana','ascii'):
            matched=[]
            def refused(line,replacement,*args,**kwargs):
                is_full=replacement[2]==FACE
                match=(target=='ascii' and line==RAW or target=='kana' and line==SOURCE)
                if is_full and match:
                    matched.append((line,replacement));return None,'independent_refusal'
                return original(line,replacement,*args,**kwargs)
            with self.subTest(target=target),patch.object(C,'_check_replacement',side_effect=refused):
                value=self.finish();self.assertTrue(matched);self.assertNotEqual(value,FACE)

    def test_cancel_after_last_actual_meaning_lookup_accept_or_reject(self):
        original=S.candidate_evidence
        for reject in (False,True):
            pending=False
            def checked(noun,head,*args,**kwargs):
                nonlocal pending
                result=original(noun,head,*args,**kwargs)
                if (noun,head)==('公園','歩き'):
                    pending=True
                    if reject:result=None
                return result
            with self.subTest(reject=reject),request_scope(lambda:pending),patch.object(S,'candidate_evidence',side_effect=checked):
                with self.assertRaises(SupersededAnalysis):self.project()

    def test_cancel_after_combined_common_gate_accept_or_reject(self):
        original=C._check_replacement
        for reject in (False,True):
            pending=False
            def checked(line,replacement,*args,**kwargs):
                nonlocal pending
                result=original(line,replacement,*args,**kwargs)
                if replacement[:3]==(0,len(SOURCE),FACE):
                    pending=True
                    if reject:result=None,'independent_refusal'
                return result
            with self.subTest(reject=reject),request_scope(lambda:pending),patch.object(C,'_check_replacement',side_effect=checked):
                with self.assertRaises(SupersededAnalysis):self.project()

    def test_cancel_after_original_ascii_common_gate_accept_or_reject(self):
        original=C._check_replacement
        for reject in (False,True):
            pending=False
            def checked(line,replacement,*args,**kwargs):
                nonlocal pending
                result=original(line,replacement,*args,**kwargs)
                if line==RAW and replacement[2]==FACE:
                    pending=True
                    if reject:result=None,'independent_refusal'
                return result
            with self.subTest(reject=reject),request_scope(lambda:pending),patch.object(C,'_check_replacement',side_effect=checked):
                with self.assertRaises(SupersededAnalysis):self.finish()

    def test_source_noun_faces_are_required_before_construction(self):
        for face in ('公演で歩きそうです','講演で歩きそうです'):
            with self.subTest(face=face):self.assertIsNone(self.construction(face=face))

    def test_absent_source_frame_is_not_permission(self):
        with patch.object(R,'native_reopened_verb_case_frames',return_value=()):
            self.assertIsNone(self.construction())

    def test_absent_actual_written_meaning_is_not_permission(self):
        original=S.candidate_evidence
        def unknown(noun,head,*args,**kwargs):
            return None if (noun,head)==('公園','歩き') else original(noun,head,*args,**kwargs)
        with patch.object(S,'candidate_evidence',side_effect=unknown):self.assertIsNone(self.construction())

    def test_active_noun_and_verb_choice_conflicts_stop_construction(self):
        for reading,chosen in (('こうえん','講演'),('あるき','行き')):
            with self.subTest(reading=reading),patch('last_choice.surface_for_reading',side_effect=lambda rd:chosen if rd==reading else None):
                self.assertIsNone(self.construction())

    def test_explicit_unit_choice_stops_construction(self):
        self.state.choices.remember('あるき','行き');self.assertIsNone(self.construction())

    def test_word_only_reject_and_protect_stop_construction(self):
        from decisions import DecisionStore
        for reading,face in (('こうえん','公園'),('あるき','歩き')):
            for action in ('protect','reject'):
                self.state.decisions=DecisionStore()
                getattr(self.state.decisions,action)(reading,*(() if action=='protect' else (face,)))
                with self.subTest(reading=reading,action=action):self.assertIsNone(self.construction())

    def test_wrong_whole_inverse_never_reaches_the_combined_first_gate(self):
        original=C._check_replacement;combined=[]
        def checked(line,replacement,*args,**kwargs):
            if replacement[:3]==(0,len(SOURCE),FACE):combined.append(replacement)
            return original(line,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=checked):
            value,_=self.project(inverse='こうえんでであるきそうです')
        self.assertEqual(combined,[]);self.assertNotEqual(value and value[0],FACE)

    def test_unproved_bare_manner_incomplete_copula_and_dearuku_cannot_construct_a_pair(self):
        for source in ('こうえんであるきそう','こうえんであるきそうで','こうえんであるき',
                       'こうえんである','こうえんでであるきます'):
            with self.subTest(source=source):self.assertIsNone(self.construction(source))

    def test_combined_gate_refusals_cannot_publish_the_full_candidate(self):
        original=C._check_replacement
        for reason in ('independent_refusal','native_auxiliary_chain','different_reason'):
            def refused(line,replacement,*args,**kwargs):
                if replacement[:3]==(0,len(SOURCE),FACE):return None,reason
                return original(line,replacement,*args,**kwargs)
            with self.subTest(reason=reason),patch.object(C,'_check_replacement',side_effect=refused):
                value,_=self.project();self.assertNotEqual(value and value[0],FACE)


# This class supplies one synthetic source-frame premise. It is a gate
# contract with real native lexical/meaning resources, not precision evidence.
@unittest.skipUnless(M.HAS_JANOME, 'actual bundled dictionary required')
class IndependentFirstCaseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(Path(__file__).absolute().with_name(
            'tests_ime_first_case_actual_predicate_fixture.json').read_text(encoding='utf-8'))
        cls.source = fixture['source']
        cls.first = fixture['conversion'][0]
        cls.descriptors = tuple(tuple(row) for row in fixture['conversion'][1])
        cls.original_parts = M.tokenize(cls.source)
        cls.parts = M.tokenize(cls.first)
        bounds = I.native_spelling_boundaries(cls.source, cls.parts)
        cls.noun = next(t for t in cls.parts if t.start == 0 and t.pos == '名詞')
        cls.case = next(t for t in cls.parts if t.start == cls.noun.end and t.pos == '助詞')
        cls.head = next(t for t in cls.parts if t.start == cls.case.end and t.pos == '動詞')
        cls.start, cls.end = bounds[cls.noun.start, cls.noun.end]
        cls.head_start, cls.head_end = bounds[cls.head.start, cls.head.end]
        cls.frame = (0, cls.source, cls.start, cls.end, cls.case.surface, (cls.noun.surface,))

    def setUp(self):
        self.state = initial()
        self.addCleanup(set_active, None)

    def construction(self, face=None, frames=None, descriptors=None):
        face = self.first if face is None else face
        parts = M.tokenize(face)
        calls = []
        original = S.candidate_evidence
        def checked(*args, **kwargs):
            answer = original(*args, **kwargs)
            calls.append((args, kwargs, answer))
            return answer
        with patch.object(R, 'native_reopened_verb_case_frames',
                          return_value=(self.frame,) if frames is None else frames), \
                patch.object(S, 'candidate_evidence', side_effect=checked):
            result = I._first_case_word_proposal(self.source, face,
                self.descriptors if descriptors is None else descriptors,
                parts, self.original_parts, I.native_spelling_boundaries(self.source, parts),
                self.state.decisions)
        return result, calls

    def test_same_reading_different_actual_predicate_reaches_its_own_meaning_gate(self):
        self.assertEqual(R.native_reopened_verb_case_frames(self.source), ())
        allowed, calls = self.construction()
        self.assertIsNotNone(allowed)
        self.assertEqual(allowed[0], self.first)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][:2], (self.noun.surface, self.head.surface))
        self.assertTrue(calls[0][2]['shared_roles'])
        other = self.first[:self.head.start] + '生き' + self.first[self.head.end:]
        other_head = next(t for t in M.tokenize(other) if t.start == self.head.start)
        self.assertEqual(other_head.reading, self.head.reading)
        self.assertEqual((other_head.start, other_head.end), (self.head.start, self.head.end))
        refused, calls = self.construction(other)
        self.assertIsNone(refused)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][:2], (self.noun.surface, '生き'))
        self.assertEqual(calls[0][2]['shared_roles'], [])

    def test_same_reading_explicit_choice_and_partial_block_override_the_pair(self):
        reading = self.source[self.head_start:self.head_end]
        self.state.choices.remember(reading, '生き')
        refused, calls = self.construction()
        self.assertIsNone(refused)
        self.assertEqual(calls, [])
        self.state = initial()
        self.state.decisions.protect(self.source[self.end - 2:self.head_end])
        # This protection overlaps the noun/case/head seam, outside either
        # isolated word. The combined common gate must retain it.
        allowed, calls = self.construction()
        self.assertIsNotNone(allowed)
        self.assertEqual(len(calls), 1)
        import corrector as C
        original_gate = C._check_replacement
        combined_gates = []
        def checked(line, edit, *args, **kwargs):
            answer = original_gate(line, edit, *args, **kwargs)
            if line == self.source and edit[:3] == (0, len(self.source), self.first):
                combined_gates.append(answer)
            return answer
        from types import SimpleNamespace
        ime = SimpleNamespace(available=True)
        ime.convert_words = lambda reading: (self.first, self.descriptors) if reading == self.source else None
        fixture = json.loads(Path(__file__).absolute().with_name(
            'tests_ime_first_case_actual_predicate_fixture.json').read_text(encoding='utf-8'))
        ime.reverse_words = lambda text: fixture['inverse'] if text == self.first else None
        ime.homophones = lambda *args, **kwargs: ()
        class NativeSession:
            def __enter__(self): return ime
            def __exit__(self, *args): return False
        with patch('ime_language.JapaneseIME', return_value=NativeSession()), \
                patch.object(R, 'native_reopened_verb_case_frames', return_value=(self.frame,)), \
                patch.object(C, '_check_replacement', side_effect=checked):
            result = I.project_first_words(self.source, self.state.store, self.state.dict_index,
                self.state.decisions, C.make_tokenizer(self.state.store))
        self.assertTrue(combined_gates)
        self.assertIsNone(combined_gates[0][0])
        self.assertNotEqual(result and result[0], self.first)

    def test_frame_from_a_different_source_position_or_clause_cannot_be_borrowed(self):
        for frame in ((1, self.source, *self.frame[2:]),
                      (0, self.source + '\t' + self.source, *self.frame[2:]),
                      (0, self.source, self.start + 1, self.end + 1, *self.frame[4:])):
            with self.subTest(frame=frame):
                result, calls = self.construction(frames=(frame,))
                self.assertIsNone(result)
                self.assertEqual(calls, [])

    def test_native_descriptor_conflict_cannot_move_the_original_noun(self):
        descriptors = tuple((a, b, c + 1, d + 1, *rest)
                            if a < self.noun.end else (a, b, c, d, *rest)
                            for a, b, c, d, *rest in self.descriptors)
        result, calls = self.construction(descriptors=descriptors)
        self.assertIsNone(result)
        self.assertEqual(calls, [])


if __name__=='__main__':unittest.main()
