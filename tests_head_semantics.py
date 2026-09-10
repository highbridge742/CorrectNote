# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock,patch
import corrector as C
import kango_tier as K
import dict_index as D

class HeadSemanticsTests(unittest.TestCase):
    def test_common_noun_is_not_pruned_solely_for_high_cost(self):
        self.assertFalse(D._should_prune('手動','名詞','一般','',9000))
        with patch.object(K,'tier',return_value=3):
            self.assertTrue(D._should_prune('手動','名詞','一般','',9000))
        self.assertTrue(D._should_prune('手動','名詞','固有名詞','人名',9000))

    def test_added_common_noun_stays_in_post_anomaly_band(self):
        idx=D.DictIndex(cache_path='unused_semantic_test_cache.json')
        with patch.object(D,'iter_janome_entries',return_value=iter([
                ('手動','しゅどう','名詞','一般','',9000)])):
            idx._build()
        self.assertIn('手動',idx.surfaces_for_reading('しゅどう'))
        self.assertNotIn('手動',idx.surfaces_for_reading('しゅどう',band=False))

    def test_sparse_cost_table_is_supplemented_by_dictionary(self):
        store=Mock();store.lookup.return_value=[]
        dictionary=Mock();dictionary.surfaces_for_reading.return_value=['主導','手動']
        with patch.object(C,'table_surfaces_for_reading',return_value=['主導']), \
             patch.object(C,'_kango_tier_of',return_value=2), \
             patch.object(C,'_table_cost',return_value=100):
            self.assertEqual(C._known_head_kanji('しゅどう',store,right_surface='調整',dict_index=dictionary),'手動')

    def test_common_semantic_class_fills_cost_sample_omissions(self):
        self.assertLessEqual(K.tier('手動'),2)
        self.assertLessEqual(K.tier('自動'),2)
        self.assertEqual(K.tier('未登録仮語'),3)

    def test_operation_mode_wins_only_with_matching_action(self):
        store=Mock();store.lookup.return_value=[]
        with patch.object(C,'table_surfaces_for_reading',return_value=['主導','手動']), \
             patch.object(C,'_kango_tier_of',return_value=1), \
             patch.object(C,'_table_cost',side_effect=lambda s:100 if s=='主導' else 200):
            self.assertEqual(C._known_head_kanji('しゅどう',store),'主導')
            self.assertEqual(C._known_head_kanji('しゅどう',store,right_surface='調整'),'手動')
            self.assertEqual(C._known_head_kanji('しゅどう',store,right_surface='権限'),'主導')

    def test_semantic_relation_is_a_class_not_a_correction_pair(self):
        for head in ('自動','手動','逐次','遠隔'):
            for tail in ('調整','制御','更新'):
                self.assertEqual(K.affinity(head,tail),2)
        self.assertEqual(K.affinity('主導','調整'),0)
        self.assertEqual(K.affinity('手動','権限'),0)

    def test_diagnosis_records_semantic_selection(self):
        store=Mock();store.lookup.return_value=[]
        with patch.object(C,'table_surfaces_for_reading',return_value=['主導','手動']), \
             patch.object(C,'_kango_tier_of',return_value=2), \
             patch.object(C,'_table_cost',side_effect=lambda s:100 if s=='主導' else 200), \
             patch.object(C,'_trace') as trace:
            self.assertEqual(C._known_head_kanji('しゅどう',store,right_surface='調整'),'手動')
        category,detail=trace.call_args.args
        self.assertEqual(category,'複合語の前半順位')
        self.assertIn("従来='主導'",detail)
        self.assertIn("採用='手動'",detail)
        self.assertIn('意味関係=2',detail)

    def test_missing_relation_retains_existing_choice(self):
        store=Mock();store.lookup.return_value=[]
        with patch.object(C,'table_surfaces_for_reading',return_value=['主導','手動']), \
             patch.object(C,'_kango_tier_of',return_value=1), \
             patch.object(C,'_table_cost',side_effect=lambda s:100 if s=='主導' else 200), \
             patch.object(K,'affinity',return_value=0):
            self.assertEqual(C._known_head_kanji('しゅどう',store,right_surface='調整'),'主導')

if __name__=='__main__':unittest.main()
