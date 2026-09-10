# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock,patch
import corrector as C

class PreservedHeadTests(unittest.TestCase):
    def resolve(self,head=('かな','かな'),reading='にゅうりょく',edits=1,odd=False):
        store=Mock();store.has_reading.side_effect=lambda r:r=='かな'
        dictionary=Mock();dictionary.is_world_reading.return_value=False
        with patch('kango_tier.tier',return_value=1), \
             patch('oddness.is_odd_run',return_value=[('x','y')] if odd else []), \
             patch.object(C,'_convert_odd_kana_run',return_value=('入力','隣接キー')):
            return C._fix_known_head_compound('かなりゅうりょく',store,lambda x:[],dictionary,
                find_readings=lambda *a:[(reading,1.0,edits)],preserved_head=head)

    def test_inflected_source_head_does_not_need_noun_index_entry(self):
        store=Mock();store.has_reading.return_value=False
        dictionary=Mock();dictionary.is_world_reading.return_value=False
        with patch('kango_tier.tier',return_value=1), \
             patch('oddness.is_odd_run',return_value=[]), \
             patch.object(C,'_convert_odd_kana_run',return_value=('入力','隣接キー')):
            result=C._fix_known_head_compound('よみこみりゅうりょく',store,lambda x:[],dictionary,
                find_readings=lambda *a:[('にゅうりょく',1.0,1)],preserved_head=('よみこみ','読み込み'))
        self.assertEqual(result,'読み込み入力')

    def test_confirmed_hiragana_surface_is_preserved(self):
        self.assertEqual(self.resolve(),'かな入力')

    def test_confirmed_katakana_surface_is_preserved(self):
        self.assertEqual(self.resolve(('かな','カナ')),'カナ入力')

    def test_no_short_prefix_guess_without_source_evidence(self):
        self.assertIsNone(self.resolve(None))

    def test_no_deletion_or_multiple_edits(self):
        self.assertIsNone(self.resolve(reading='にゅうりょ'))
        self.assertIsNone(self.resolve(edits=2))

    def test_generated_odd_compound_is_rejected(self):
        self.assertIsNone(self.resolve(odd=True))

if __name__=='__main__':unittest.main()
