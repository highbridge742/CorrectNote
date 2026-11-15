# -*- coding: utf-8 -*-
"""Reopen source-proved choices after a displayed or literal replacement."""
import unittest
from unittest.mock import Mock
import app,candidates
import tests_particle_candidates as fixtures
from last_choice import LastChoiceStore
from decisions import DecisionStore
from analysis_work import observe_text
import analysis_work_app as work


class ReselectionTests(unittest.TestCase):
    # 学んだ選び（最後の選択）を使う試験。2026-11-08 から既定で使わない（CN_LEARNED_HISTORY=1 で使う）ので、
    # この試験の間だけ last_choice・vocabulary の LEARNED_OFF を外す（2026-11-14 補正担当、うに 10:44Z「2.よいです」）
    @classmethod
    def setUpClass(cls):
        import last_choice,vocabulary
        cls._lh=(last_choice.LEARNED_OFF,vocabulary.LEARNED_OFF)
        last_choice.LEARNED_OFF=False;vocabulary.LEARNED_OFF=False
    @classmethod
    def tearDownClass(cls):
        import last_choice,vocabulary
        last_choice.LEARNED_OFF,vocabulary.LEARNED_OFF=cls._lh
    tearDown=fixtures.ParticleChoiceTkTests.tearDown
    def setUp(self):
        fixtures.ParticleChoiceTkTests.setUp(self)
        a=self.a;a.decisions=DecisionStore();a.choices=LastChoiceStore();a.choices.save=Mock()
        self.source='文章をきうしします。';self.base='きうしします'
        self.result=dict(original=self.source,corrected='文章をきいてします。',details=[],
            contextual_choices=dict(version=1,source=self.source,input_method='kana',candidates=[
                dict(start=3,end=9,base=self.base,surface=s,reading='そうしんします')
                for s in ('送信します','そうしんします')]))
        a.line_results=[self.result];a._quick_results=[self.result]
    def contents(self,w):return w.get('1.0','end-1c')
    def choices(self,w):
        text=self.contents(w);u=app.make_range_unit(text,[],3,len(text)-1)
        return u,self.a._contextual_choice_candidates(1,u,w,[u])
    def test_explicit_projection_reopens_in_result_and_rejects_unproved_display(self):
        a=self.a;w=a.result_view
        a.choices.record(self.base,'送信します')
        shown='文章を送信します。';w.delete('1.0','end');w.insert('1.0',shown)
        unit,found=self.choices(w)
        self.assertEqual([c['surface'] for c in found],['そうしんします'])
        a._choose_word(unit,found[0],1)
        self.assertEqual(a.choices.lookup(self.base),'そうしんします')
        w.delete('1.0','end');w.insert('1.0','文章をそうしんします。')
        self.assertEqual([c['surface'] for c in self.choices(w)[1]],['送信します'])
        for text in ('別文をそうしんします。','文章を送信しました。'):
            self.assertFalse(candidates.contextual_choice_candidates(self.result,text,3,len(text)-1,a.choices))
    def test_literal_input_choice_reopens_after_analysis_replaces_results(self):
        a=self.a
        for pane in ('editor','quick'):
            with self.subTest(pane=pane):
                w=a.editor if pane=='editor' else a._quick_text
                w.delete('1.0','end');w.insert('1.0',self.source)
                a.line_results=[self.result];a._quick_results=[self.result]
                choose=a._editor_choose_word if pane=='editor' else a._quick_choose_word
                unit,found=self.choices(w);choose(1,unit,next(c for c in found if c['surface']=='送信します'))
                self.assertEqual(self.contents(w),'文章を送信します。')
                # A fresh analysis of already-correct text has no typo proof.
                a.line_results=[{}];a._quick_results=[{}]
                unit,found=self.choices(w)
                self.assertEqual([c['surface'] for c in found],['そうしんします'])
                choose(1,unit,found[0])
                self.assertEqual(self.contents(w),'文章をそうしんします。')
                self.assertEqual(a.choices.lookup(self.base),'そうしんします')
                self.assertEqual([c['surface'] for c in self.choices(w)[1]],['送信します'])
    def test_edit_aba_or_new_rejection_invalidates_retained_proof(self):
        a=self.a;w=a._quick_text
        w.delete('1.0','end');w.insert('1.0',self.source)
        work.quick_document(a,self.source)
        observe_text(w,lambda text,discard,edit:work.quick_edited(a,text,discard,edit))
        unit,found=self.choices(w);a._quick_choose_word(1,unit,next(c for c in found if c['surface']=='送信します'))
        a._quick_results=[{}]
        unit,found=self.choices(w);self.assertTrue(found)
        candidate=found[0]
        a.decisions.reject('きうし','そうしん');self.assertFalse(self.choices(w)[1])
        a.decisions=DecisionStore()
        text=self.contents(w);w.delete('1.0','end');w.insert('1.0',text)
        self.assertFalse(self.choices(w)[1])
        self.assertIsNone(a._candidate_selection_unit(1,unit,candidate,w))
    def test_lengths_before_another_candidate_are_projected(self):
        result=dict(original='甲ああ乙いい',corrected='甲ああ乙いい',contextual_choices=dict(
            version=1,source='甲ああ乙いい',candidates=[
                dict(start=1,end=3,base='ああ',surface='長い語'),
                dict(start=4,end=6,base='いい',surface='第二'),
                dict(start=4,end=6,base='いい',surface='だいに')]))
        self.a.choices.record('ああ','長い語');self.a.choices.record('いい','第二')
        found=candidates.contextual_choice_candidates(result,'甲長い語乙第二',5,7,self.a.choices)
        self.assertEqual([(c['surface'],c['choice_span']) for c in found],[('だいに',(5,7))])
