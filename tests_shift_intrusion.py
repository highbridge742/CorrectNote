# -*- coding: utf-8 -*-
"""Only source-required Shift can witness deletion of its adjacent key."""
import unittest
from unittest.mock import patch
import kana_layout as K,contextual_repair as Q,corrector as C
class SourceShiftIntrusionTests(unittest.TestCase):
    def test_source_small_kana_supplies_its_real_modifier(self):
        for before,after in (('もーしろょん','もーしょん'),('もーしょろん','もーしょん'),('りつゅう','りゅう'),('りろゅう','りゅう')):
            with self.subTest(before=before):
                self.assertTrue(K.single_key_drop_adjacency(before,after))
                self.assertFalse(K.single_key_drop_is_duplicate(before,after))
                self.assertIn(after,C._typo_repairs_intruded(before))
                rows=[r for r in Q.key_repairs(before) if r.reading==after]
                self.assertTrue(rows)
                self.assertEqual(rows[0].operation,'adjacent_intrusion')
                self.assertTrue(Q._original_intrusion_allowed(before,rows[0]))
    def test_deletion_keeps_original_shift_while_adjacent_printed_keys_can_differ(self):
        self.assertGreater(K.kana_key_distance('よ','ゅ'),1.0)
        self.assertEqual(K.intrusion_key_distance('よ','ゅ'),1.0)
        self.assertTrue(K.single_key_drop_adjacency('ちよゅう','ちゅう'))
        self.assertIn('ちゅう',C._typo_repairs_intruded('ちよゅう'))
        self.assertTrue(any(r.reading=='ちゅう' and r.operation=='adjacent_intrusion'
                            for r in Q.key_repairs('ちよゅう')))

    def test_ordinary_and_nonadjacent_source_does_not_invent_shift(self):
        for before,after in (('もーしろよん','もーしよん'),('りろゆう','りゆう'),('もんじにゅうりょく','もじにゅうりょく'),('りこゅう','りゅう')):
            with self.subTest(before=before):
                self.assertFalse(K.single_key_drop_adjacency(before,after))
                self.assertNotIn(after,C._typo_repairs_intruded(before))
                self.assertFalse(any(r.reading==after for r in Q.key_repairs(before)))
        invented=Q.KeyRepair('もーしょん','adjacent_intrusion',3,'ろ','',1.0)
        self.assertFalse(Q._original_intrusion_allowed('もーしろよん',invented))
        self.assertGreater(K.kana_key_distance('ろ','ょ'),1.0)
        self.assertGreater(K.intrusion_key_distance('ょ','ろ'),1.0)
    def test_legacy_generator_does_not_infer_a_kana_shift_in_romaji_mode(self):
        token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            self.assertNotIn('もーしょん',C._typo_repairs_intruded('もーしろょん'))
            self.assertIn('がぞう',C._typo_repairs_intruded('がすぞう'))
        finally:C._CORRECTION_INPUT_METHOD.reset(token)
        self.assertIn('もーしょん',C._typo_repairs_intruded('もーしろょん'))

    def test_window_boundary_and_duplicate_policy_use_original_keys(self):
        repair=Q.KeyRepair('','adjacent_intrusion',0,'ろ','',1.0)
        self.assertTrue(Q._original_intrusion_allowed('ろ',repair,after='ょん'))
        self.assertFalse(Q._original_intrusion_allowed('ろ',repair,after='よん'))
        with patch('vocabulary.dup_repair_enabled',return_value=False):
            self.assertFalse(any(r.reading=='ちょう' for r in Q.key_repairs('ちょょう')))
if __name__=='__main__':unittest.main()
