# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Exact effective original unit ownership; no chosen face becomes grammar proof."""
import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,units as U
from last_choice import LastChoiceStore

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class MixedChoiceScopeTests(unittest.TestCase):
    source='スくりーんをくたせさい。'
    def bound(self,line,*choices):
        store=LastChoiceStore()
        for base,face in choices:self.assertTrue(store.remember(base,face))
        return tuple(U._find_choice_ranges(line,(),store))
    def allowed(self,line,edit,bindings,nominal=0,predicate=6,faces=('スクリーン',)):
        return R.native_mixed_object_choice_preserved(line,*edit,nominal,predicate,faces,bindings)
    def test_conflicting_exact_unit_keeps_its_literal_source(self):
        b=self.bound(self.source,('くたせさい','下さい'))
        self.assertFalse(self.allowed(self.source,(6,11,'ください'),b))
        self.assertTrue(self.allowed(self.source,(6,11,'くたせさい'),b))
    def test_exact_already_c_validated_choice_can_represent_the_unit(self):
        b=self.bound(self.source,('くたせさい','ください'))
        self.assertTrue(self.allowed(self.source,(6,11,'ください'),b))
        self.assertFalse(self.allowed(self.source,(6,11,'下さい'),b))
    def test_partial_unit_and_longest_owner_cannot_donate_an_interior(self):
        partial=self.bound(self.source,('たせさい','下さい'))
        self.assertFalse(self.allowed(self.source,(6,11,'ください'),partial))
        whole=self.bound(self.source,('くたせさい','ください'),('スくりーんをくたせさい','画面を下さい'))
        self.assertEqual(whole,((0,11,'スくりーんをくたせさい','画面を下さい'),))
        self.assertFalse(self.allowed(self.source,(6,11,'ください'),whole))
    def test_whole_owner_crossing_tab_keeps_original_longest_binding(self):
        line=self.source+'\tシャつをくたせさい。'
        b=self.bound(line,('くたせさい','ください'),('スくりーんをくたせさい。\tシャつ','画面を下さい。\t衣服'))
        self.assertFalse(self.allowed(line,(6,11,'ください'),b))
        self.assertTrue(self.allowed(line,(17,22,'ください'),b,13,17,('シャツ',)))
    def test_same_base_at_two_original_positions_and_other_field_are_separate(self):
        line=self.source+'\t'+self.source
        b=self.bound(line,('くたせさい','下さい'))
        self.assertFalse(self.allowed(line,(6,11,'ください'),b))
        self.assertFalse(self.allowed(line,(19,24,'ください'),b,13,19))
        only_second=self.bound(line,('スくりーんをくたせさい。\tスくりーん','画面を下さい。\t画面'))
        self.assertTrue(self.allowed(line,(19,24,'ください'),only_second,13,19))
    def test_immutable_bindings_change_without_reusing_a_previous_choice_answer(self):
        wrong=self.bound(self.source,('くたせさい','下さい'))
        same=self.bound(self.source,('くたせさい','ください'))
        for b,answer in ((wrong,False),(same,True),((),True),(wrong,False)):
            self.assertEqual(self.allowed(self.source,(6,11,'ください'),b),answer)
    def test_nominal_partial_choice_and_unrelated_source_face_are_not_consumed(self):
        nominal=self.bound(self.source,('りーん','リーン'))
        self.assertTrue(self.allowed(self.source,(6,11,'ください'),nominal))
        conflict=self.bound(self.source,('くたせさい','下さい'))
        self.assertTrue(self.allowed(self.source,(6,11,'ください'),conflict,faces=('幕',)))
        # No newly proved mixed source: this helper does not redesign prior routes.
        plain='スクリーンをくたせさい。'
        self.assertTrue(self.allowed(plain,(6,11,'ください'),self.bound(plain,('くたせさい','下さい'))))
    def test_original_unicode_clause_offset_is_used_before_any_display_shortening(self):
        prefix='👩🏽\u200d💻e\u0301\tひらがな。';line=prefix+self.source;offset=len(prefix)
        b=self.bound(line,('くたせさい','下さい'),('スくりーん','画面'))
        self.assertFalse(self.allowed(line,(offset+6,offset+11,'ください'),b,offset,offset+6))
        self.assertTrue(self.allowed(line,(offset+6,offset+11,'くたせさい'),b,offset,offset+6))
    def test_ordinary_object_frames_do_not_scan_full_source_choices(self):
        import contextual_repair as Q
        from last_choice import set_active
        store=LastChoiceStore();store.remember('くたせさい','下さい')
        set_active(store);self.addCleanup(set_active,None)
        # Both frames reach the same final object proof; only the newly
        # supported whole mixed noun needs literal choice ownership here.
        for line,face,expected in (('スクリーンをくたせさい。','スクリーン',False),
                                   ('スくりーんをくたせさい。','スクリーン',True)):
            with self.subTest(line=line), \
                    patch.object(Q,'_source_object_predicate_frame',return_value=(0,len(line),0,6,(face,))), \
                    patch.object(Q,'_changed_genitive_object_allowed',return_value=True), \
                    patch.object(Q,'_later_object_scope',return_value=None), \
                    patch.object(U,'_find_choice_ranges',return_value=()) as scan, \
                    patch.object(Q,'_object_predicate_candidate_fits',return_value=True):
                Q.object_predicate_candidate_allowed(line,6,11,'ください')
                self.assertEqual(scan.called,expected)

    def test_source_request_boundary_rechecks_original_choice_after_native_acceptance(self):
        import contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from correction_entry import correct_line
        from last_choice import set_active
        a=initial();self.addCleanup(set_active,None)
        a.choices.remember('くたせさい','下さい','ください')
        revision=a.choices.revision();calls=[];original=R.native_mixed_object_choice_preserved
        def guard(*args):
            answer=original(*args);calls.append((args,answer));return answer
        with patch.object(R,'native_mixed_object_choice_preserved',side_effect=guard):
            result=correct_line(self.source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],self.source)
        self.assertTrue(any(args[3]=='ください' and not answer for args,answer in calls))
        self.assertEqual(a.choices.revision(),revision)
        shown,units=U.build_line_units(result,C.make_tokenizer(a.store),a.choices)
        self.assertEqual(shown,'スくりーんを下さい。')
        self.assertEqual([(u['base'],u['text']) for u in units if u['kind']=='chosen'],[('くたせさい','下さい')])

if __name__=='__main__':unittest.main()
