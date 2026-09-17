# -*- coding: utf-8 -*-
"""The disabled repeated-key operation also applies to fallback generators."""
import os
import unittest
from unittest.mock import patch
import corrector as C
import kana_layout as K


class DuplicatePolicyTests(unittest.TestCase):
    def lu_readings(self,text,enabled):
        seen=set()
        with patch.dict(os.environ,{'CN_NO_DUP':'0' if enabled else '1'}), \
             patch.object(C,'_lu_dominant',side_effect=lambda rd,*args: seen.add(rd)), \
             patch.object(K,'nearby_candidates',return_value=[]), \
             patch.object(C,'_moved_dakuten_variants',return_value=[]):
            C._lu_compose_odd_run(text,object(),input_method='kana',odd_known=True)
        return seen

    def test_pure_deletion_requires_a_neighboring_physical_key(self):
        with patch.object(C,'_ADJ_GATE',True):
            self.assertFalse(C._adj_ok_one_char('もんじにゅうりょく','もじにゅうりょく','kana'))
            self.assertFalse(C._adj_ok_one_char('せつめ','せめ','kana'))
            self.assertFalse(C._adj_ok_one_char('ふっら','ふら','kana'))
            self.assertTrue(C._adj_ok_one_char('さつぎょう','さぎょう','kana'))
            self.assertTrue(C._adj_ok_one_char('さきげょう','さぎょう','kana'))
            self.assertTrue(C._adj_ok_one_char('せつめ','せつめい','kana'))
            self.assertTrue(C._adj_ok_one_char('せつめ','せめ','romaji'))

    def test_lu_respects_the_duplicate_setting_before_looking_for_words(self):
        for source,collapsed in (('べいここく','べいこく'),('でぃれれくた','でぃれくた')):
            self.assertNotIn(collapsed,self.lu_readings(source,False))
            self.assertIn(collapsed,self.lu_readings(source,True))

    def test_an_equal_neighbor_is_not_disguised_as_an_intrusion_from_the_other_side(self):
        for source,collapsed in (('べいここく','べいこく'),('さつつい','さつい')):
            with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
                self.assertNotIn(collapsed,C._typo_repairs(source,extra_key=True))
            with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
                self.assertIn(collapsed,C._typo_repairs(source,extra_key=True))

    def test_distinct_adjacent_key_intrusions_are_available_in_both_settings(self):
        for enabled in (False,True):
            self.assertIn('さいだいか',self.lu_readings('さついだいか',enabled))
            with patch.dict(os.environ,{'CN_NO_DUP':'0' if enabled else '1'}):
                self.assertIn('さいだいか',C._typo_repairs('さついだいか',extra_key=True))

    def test_every_equal_length_substitution_must_be_adjacent(self):
        with patch.object(C,'_ADJ_GATE',True):
            self.assertFalse(C._adj_ok_one_char('たたんご','らてんご','kana'))
            self.assertTrue(C._adj_ok_one_char('たごん','たんご','kana'))
            self.assertTrue(C._adj_ok_one_char('たつ','ちつ','kana'))

    def test_settings_are_part_of_both_reading_caches(self):
        import vocabulary as V
        from tests_mock_common import build_store
        store=build_store([('べいこく','米国'),('でぃれくた','ディレクタ')])
        V._FLEX_CACHE.clear();V._SIM_CACHE.clear()
        for trie in (False,True):
            with patch.object(V,'_USE_TRIE',trie):
                for enabled in (True,False,True):
                    with patch.dict(os.environ,{'CN_NO_DUP':'0' if enabled else '1'}):
                        flex=V.find_known_readings_flex('べいここく',store,max_dist=4,max_edits=2,input_method='kana')
                        similar=V.find_similar_readings('でぃれれくた',store,max_cost=4,limit=100)
                    self.assertEqual('べいこく' in {r[0] for r in flex},enabled)
                    self.assertEqual('でぃれくた' in {r[0] for r in similar},enabled)
            V._SIM_CACHE.clear()

    def test_complete_word_removal_is_not_mislabelled_as_duplicate_collapse(self):
        import vocabulary as V
        self.assertTrue(V.is_repeat_collapse('たたんご','たんご'))
        self.assertFalse(V.is_repeat_collapse('資料ＤＤ','資料'))
        self.assertFalse(V.is_repeat_collapse('もも','おも'))

    def test_recursive_shift_does_not_disguise_original_duplicate_deletion(self):
        original='先に表示。ひとりよよがりをみます。'
        prepared='先にひょうじ。ひとりょよがりをみます。'
        start=prepared.index('ひとり');end=start+len('ひとりょよがり')
        token=C._CORRECTION_PATH.set((original,prepared))
        try:
            with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
                accepted,reason=C._check_replacement(prepared,
                    (start,end,'ひとりよがり','かな入力'),None,None)
                self.assertIsNone(accepted)
                self.assertEqual(reason,'duplicate_repair_disabled')
                self.assertFalse(C._repeat_repair_disabled_in_source(
                    prepared,start,end,'ひとりょうがり'))
            with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
                self.assertFalse(C._repeat_repair_disabled_in_source(
                    prepared,start,end,'ひとりよがり'))
        finally:
            C._CORRECTION_PATH.reset(token)

    def test_source_mapping_does_not_guess_inside_a_rewritten_word(self):
        token=C._CORRECTION_PATH.set(('ひとりよよがり。','一人ょよがり。'))
        try:
            with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
                self.assertFalse(C._repeat_repair_disabled_in_source(
                    '一人ょよがり。',1,6,'人よがり'))
        finally:
            C._CORRECTION_PATH.reset(token)

    def test_voicing_does_not_hide_a_repeated_physical_key(self):
        for source,target in (('ほそぞん','ほぞん'),('きっふぷ','きっぷ'),('ふぷ','ぷ')):
            self.assertTrue(K.single_key_drop_is_duplicate(source,target))
            with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
                self.assertEqual(C._check_replacement(source,(0,len(source),target,'かな入力'),None,None),
                                 (None,'duplicate_repair_disabled'))
            with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
                self.assertFalse(C._repeat_repair_disabled_in_source(source,0,len(source),target))
        self.assertFalse(K.single_key_drop_is_duplicate('さつぎょう','さぎょう'))
        self.assertIsNone(K.single_key_drop_is_duplicate('が','か'))

    def test_physical_repetition_uses_original_neighbor_outside_the_span(self):
        with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
            self.assertEqual(C._check_replacement('ほそぞん',(1,2,'','かな入力'),None,None),
                             (None,'duplicate_repair_disabled'))

    def test_kanji_replacement_keeps_repetition_policy_from_its_reading(self):
        def known(text):return [(text,'名詞:サ変接続','ほぞん',0,len(text),True,'')]
        with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
            self.assertEqual(C._check_replacement('ほそぞん',(0,4,'保存','かな入力'),None,known),
                             (None,'duplicate_repair_disabled'))

    def test_shift_does_not_hide_the_same_physical_key(self):
        for source,target in (('みっつ','みつ'),('やゃ','や'),('ゆゅ','ゅ'),('あぁ','ぁ')):
            self.assertTrue(K.single_key_drop_is_duplicate(source,target))
            with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
                self.assertEqual(C._check_replacement(source,(0,len(source),target,'かな入力'),None,None),
                                 (None,'duplicate_repair_disabled'))
            with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
                self.assertFalse(C._repeat_repair_disabled_in_source(source,0,len(source),target))
        self.assertFalse(K.single_key_drop_is_duplicate('あゃ','あ'))
        self.assertIsNone(K.single_key_drop_is_duplicate('っ','つ'))

    def test_default_disables_duplicate_repair_without_an_environment_override(self):
        import vocabulary as V
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(V.dup_repair_enabled())
            self.assertTrue(V.repeat_collapse_is_disabled('べいここく','べいこく'))


if __name__=='__main__':unittest.main()
