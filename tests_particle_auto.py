# -*- coding: utf-8 -*-
"""Automatic intrusion proof, original-key constraints, and usable UI ranges."""
import unittest
from unittest.mock import patch
import morphology

@unittest.skipUnless(morphology.HAS_JANOME,'native Janome dictionary')
class AutomaticParticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial()

    def correct(self,text,**kwargs):
        import app
        from decisions import DecisionStore
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=kwargs.pop('decisions',DecisionStore()),
            input_method=kwargs.pop('input_method','kana'),**kwargs)

    def test_written_and_kana_topics_are_automatic(self):
        for source,wanted in (
            ('資料に気は、','資料には、'),('しりょうにきは、','しりょうには、'),
            ('文書に気は、','文書には、'),('ずめんに気は、','ずめんには、'),('ずめんにきは、','ずめんには、'),('画面にきは、','画面には、'),
            ('文書に気は見出しがあります。','文書には見出しがあります。'),
            ('ぶんしょにきはみだしがあります。','ぶんしょにはみだしがあります。'),
            ('文書に気は、注釈があります。','文書には、注釈があります。')):
            with self.subTest(source=source):
                result=self.correct(source)
                self.assertEqual(result['corrected'],wanted)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')

    def test_supported_continuations_and_unfinished_input_are_retained(self):
        for source in ('資料に気は配っています。','資料に気は、配っています。',
            '文書に気は付けてください。','資料に気は十分に配ります。',
            '絵に気は込めています。','ここに木はありません。','庭に木はあります。',
            '資料に気は','しりょうにきは','資料に気は。','庭にきは、','謎語に気は、',
            '資料に木は、','資料に気を付けます。','説明の続きは明日です。',
            'しりょうにきはくばっています。','資料に気はあると思います。'):
            with self.subTest(source=source):
                self.assertEqual(self.correct(source)['corrected'],source)

    def test_nonadjacent_repeat_and_romaji_do_not_use_particle_deletion(self):
        from particle_frames import interrupted_topic_frames
        for source in ('資料にんは、','資料にには、','資料にはは、','資料にぎは、'):
            with self.subTest(source=source):
                self.assertFalse(interrupted_topic_frames(source,self.a.dict_index))
                self.assertNotEqual(self.correct(source)['corrected'],'資料には、')
        self.assertEqual(self.correct('資料に気は、',input_method='romaji')['corrected'],'資料に気は、')

    def test_source_proof_precedes_physical_search_and_shared_final_validation(self):
        import corrector
        from particle_frames import interrupted_topic_frames
        with patch('kana_layout.single_key_drop_adjacency',side_effect=AssertionError('key search before source proof')):
            self.assertTrue(interrupted_topic_frames('資料に気は、',self.a.dict_index))
        with patch.object(corrector,'_chunk_is_intact',wraps=corrector._chunk_is_intact) as intact, \
             patch.object(corrector,'_check_replacement',wraps=corrector._check_replacement) as final:
            self.assertEqual(self.correct('資料に気は、')['corrected'],'資料には、')
        self.assertTrue(any(c.kwargs.get('repair_context') is not None and
            c.kwargs['repair_context'].boundary_kind=='particle_intrusion' for c in intact.call_args_list))
        self.assertTrue(any(len(c.args)>1 and c.args[1][:3]==(0,5,'資料には') for c in final.call_args_list))
        with patch('kana_layout.single_key_drop_adjacency',return_value=False):
            result=self.correct('資料に気は、')
            self.assertEqual(result['corrected'],'資料に気は、')
            self.assertTrue(result['odd_spans'])
            columns=self.correct('資料に気は、  文書に気は、')
            self.assertEqual(columns['corrected'],'資料に気は、  文書に気は、')
            self.assertTrue(any(a<=2 and b>=5 for a,b in columns['odd_spans']))
            self.assertTrue(any(a<=10 and b>=13 for a,b in columns['odd_spans']))

    def test_rejection_protection_and_purple_only_are_distinct(self):
        from decisions import DecisionStore
        for protect in (False,True):
            ledger=DecisionStore()
            if protect:ledger.protect('資料に気は')
            else:ledger.reject('資料に気は','資料には')
            self.assertEqual(self.correct('資料に気は、',decisions=ledger)['corrected'],'資料に気は、')
        ledger=DecisionStore();ledger.leave_odd_alone('に気は')
        self.assertEqual(self.correct('資料に気は、',decisions=ledger)['corrected'],'資料には、')
        source='入力例は「資料に気は、」です。'
        self.assertEqual(self.correct(source)['corrected'],source)

    def test_repaired_kana_topics_remain_stable_on_reanalysis(self):
        from reading_segments import native_nominal_topic_prefix
        import contextual_repair
        for source in ('ぶんしょに気は、','ずめんにきは、','ぶんしょにきはみだしがあります。'):
            first=self.correct(source)
            second=self.correct(first['corrected'])
            with self.subTest(source=source):
                self.assertNotEqual(first['corrected'],source)
                self.assertEqual(second['corrected'],first['corrected'])
                self.assertFalse(second['odd_spans'])
        self.assertEqual(native_nominal_topic_prefix('ぶんしょには、'),6)
        self.assertEqual(native_nominal_topic_prefix('ぶんしょにきは、'),0)
        self.assertEqual(native_nominal_topic_prefix('ぞぬぺには、'),0)
        self.assertFalse(contextual_repair.preserves_completed_reading_link('ぶんしょには、',0,4,'文書'))
        self.assertTrue(contextual_repair.preserves_completed_reading_link('ぶんしょには誤記があります。',6,8,'注記'))

    def test_multiple_columns_have_independent_clickable_ranges(self):
        import ui_projection
        source='資料に気は、  しりょうにきは、'
        result=self.correct(source)
        self.assertEqual(result['corrected'],'資料には、  しりょうには、')
        self.assertEqual(len(result['details']),2)
        for src in (False,True):
            text=result['original' if src else 'corrected']
            for a,b,detail in ui_projection.corrections(result,src):
                self.assertLess(a,b)
                self.assertEqual(text[a:b],detail[0 if src else 1])
                self.assertTrue(detail[0] and detail[1])
        self.assertEqual(result['details'][0][:2],('資料に気は','資料には'))

if __name__=='__main__':unittest.main()
