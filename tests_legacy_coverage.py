# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_repaired_spelling
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import morphology as M
import contextual_repair as C

class LegacyCoverageTests(unittest.TestCase):
    def test_wider_candidate_retains_original_facts_and_context(self):
        text='あぐせすもにたに行きます。'
        target=C.RepairTarget(text,0,4,0,len(text)-1,(('せ','す',2,4),),True,text[4:-1])
        rows=C._legacy_covering_targets([target],[(0,7,'アクセスモニタ')])
        self.assertIn(target,rows)
        self.assertEqual(len(rows),2)
        wide=rows[1]
        self.assertEqual((wide.start,wide.end,wide.text),(0,7,text[:7]))
        self.assertEqual(wide.anomalies,target.anomalies)
        self.assertEqual(wide.context,target.context)
        self.assertEqual(wide.following,text[7:-1])
        self.assertEqual(C._legacy_covering_targets(rows,[(0,7,'アクセスモニタ')]),rows)

    def test_existing_transposition_is_not_two_independent_display_edits(self):
        source='甲あいを読む。乙かき'
        result=dict(corrected='甲いあを読む。乙くけ',
            original_spans=[(1,3),(8,10)],spans=[(1,3),(8,10)])
        engine=SimpleNamespace(_diff_spans=lambda *args: (_ for _ in ()).throw(
            AssertionError('validated source operation was split')))
        changes=C._legacy_source_changes(source,result,engine)
        self.assertEqual(changes,[(1,3,'いあ'),(8,10,'くけ')])
        target=C.RepairTarget(source,3,6,0,7,(('い','を',2,4),),True,'。')
        retained=C._retain_independent_changes(changes,[(3,6,'読んだ')],[target])
        self.assertEqual(retained,[(8,10,'くけ')])
        self.assertEqual(C._apply(source,retained+[(3,6,'読んだ')]),'甲あい読んだ。乙くけ')

    def test_unchanged_outer_context_does_not_create_a_wider_competing_target(self):
        source='甲あいを読む。乙'
        result=dict(corrected='甲いあを読む。乙',original_spans=[(0,7)],spans=[(0,7)])
        engine=SimpleNamespace(_diff_spans=lambda *args: (_ for _ in ()).throw(
            AssertionError('atomic operation was split')))
        changes=C._legacy_source_changes(source,result,engine)
        self.assertEqual(changes,[(1,3,'いあ')])
        target=C.RepairTarget(source,1,3,0,7,(('あ','い',1,3),),True,source[3:7])
        self.assertEqual(C._legacy_covering_targets([target],changes),[target])
        self.assertEqual(C._apply(source,changes),result['corrected'])

    def test_an_unchanged_metadata_interval_is_not_a_correction(self):
        source='甲乙。'
        self.assertEqual(C._legacy_source_changes(source,dict(corrected=source,
            original_spans=[(0,2)],spans=[(0,2)]),None),[])

    def test_variable_width_operations_keep_source_and_output_coordinates(self):
        source='甲乙と丙丁。'
        result=dict(corrected='かなと字。',original_spans=[(0,2),(3,5)],spans=[(0,2),(3,4)])
        changes=C._legacy_source_changes(source,result,None)
        self.assertEqual(changes,[(0,2,'かな'),(3,5,'字')])
        self.assertEqual(C._apply(source,changes),result['corrected'])

    def test_unmatched_or_overlapping_metadata_cannot_supply_source_intervals(self):
        source='甲乙と丙丁。';corrected='かなと字。';diff=[(0,2,0,2),(3,5,3,4)]
        engine=SimpleNamespace(_diff_spans=lambda *args:diff)
        for originals,outputs in (([],[]),([(0,2)],[(0,2)]),
                ([(0,2),(1,5)],[(0,2),(3,4)]),
                ([(0,2),(3,5)],[(0,3),(3,4)]),
                ([(0,2),(3,6)],[(0,2),(3,4)]),
                ([(0,2),(3,99)],[(0,2),(3,4)])):
            with self.subTest(originals=originals,outputs=outputs):
                self.assertEqual(C._legacy_source_changes(source,dict(corrected=corrected,
                    original_spans=originals,spans=outputs),engine),[(0,2,'かな'),(3,5,'字')])

    def test_neighbor_anomaly_rechecks_the_complete_prior_operation(self):
        source='甲あいを読む。'
        target=C.RepairTarget(source,3,6,0,7,(('い','を',2,4),),True,'。')
        with patch.object(C,'validate',return_value=(True,'accepted')) as check:
            self.assertTrue(C._legacy_resolves_anomaly(target,[(1,3,'いあ')],None,None,None,None,None))
        wide,surface=check.call_args.args[:2]
        self.assertEqual((wide.start,wide.end,wide.text,surface),(1,6,'あいを読む','いあを読む'))
        with patch.object(C,'validate',return_value=(False,'nonadjacent_original_key_deletion')):
            self.assertFalse(C._legacy_resolves_anomaly(target,[(1,3,'いあ')],None,None,None,None,None))

    def test_prior_operation_must_stay_in_original_context(self):
        source='甲あいを読む。'
        target=C.RepairTarget(source,3,6,2,7,(('い','を',2,4),),True,'。')
        with patch.object(C,'validate') as check:
            self.assertFalse(C._legacy_resolves_anomaly(target,[(1,3,'いあ')],None,None,None,None,None))
        check.assert_not_called()

    def test_spelling_and_preserved_heads_do_not_expand(self):
        text='原文です。'
        target=C.RepairTarget(text,1,2,0,4,(('原','文',0,2),),True,'です')
        for guarded in (replace(target,preserved_head='文'),replace(target,spelling=('source-fact',))):
            self.assertEqual(C._legacy_covering_targets([guarded],[(0,4,'別表記')]),[guarded])
        self.assertEqual(C._legacy_covering_targets([target],[(0,5,'句点越え')]),[target])

@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class NativeLegacyCoverageTests(unittest.TestCase):
    def test_later_auxiliary_inside_a_loan_is_not_a_predicate_head(self):
        import corrector
        from tests_analysis_async import initial
        a=initial();tk=corrector.make_tokenizer(a.store)
        text='あぐせすもにたに行きます'
        target=C.RepairTarget(text,0,7,0,len(text),(),True,text[7:])
        self.assertFalse(C._source_predicate_context(target,tk))
        text='おくます'
        target=C.RepairTarget(text,0,len(text),0,len(text),(),True,'')
        self.assertTrue(C._source_predicate_context(target,tk))

    def test_wide_loan_and_kana_predicates_share_final_selection(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('あぐせすもにたに行きます。','アクセスモニタに行きます。'),
            ('アクセスモニタに行きます。','アクセスモニタに行きます。'),
            ('アクセスも確認します。','アクセスも確認します。'),
            ('まどをしめてからほんをよみんす。','まどをしめてからほんを読みます。'),
            ('おくます。','置きます。')):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                assert_repaired_spelling(self, r, expected);self.assertEqual(r['odd_spans'],[])

    def test_unchanged_auxiliary_does_not_discard_available_lexical_ranking_evidence(self):
        import corrector
        from vocabulary import find_known_readings_flex
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store);tk=corrector.make_tokenizer(a.store)
        text='説明ぶん　差釣れません。'
        result=corrector.correct_line(text,a.store,tk,find_known_readings_flex,
            dict_index=a.dict_index,input_method='kana')
        self.assertEqual(result['corrected'],'説明文　されません。')
        self.assertFalse(result['odd_spans'])

    def test_fresh_transposition_keeps_its_original_case_particle(self):
        import app,corrector
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for source,wanted in (('べんらがを確認しました。','べんがらを確認しました。'),
                ('べんがらを確認しました。','べんがらを確認しました。'),
                ('べんがらが確認しました。','べんがらが確認しました。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                assert_repaired_spelling(self, result, wanted)
                self.assertEqual(result['odd_spans'],[])
        # Protecting a complete transposition never permits its deletion half.
        source='べんらがを確認しました。';tk=corrector.make_tokenizer(a.store)
        self.assertEqual(corrector._check_replacement(source,(3,7,'を確認','かな入力'),
            a.store,tk,a.dict_index),(None,'nonadjacent_original_key_deletion'))

if __name__=='__main__':unittest.main()

