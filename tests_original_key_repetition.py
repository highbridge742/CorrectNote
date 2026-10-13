# -*- coding: utf-8 -*-
"""Literal original keys preserve their kana repetition, never a copied edge."""
import unittest
from unittest.mock import patch
import corrector as C


class OriginalKeyRepetitionTests(unittest.TestCase):
    def check(self, source, start, end, changed):
        with patch.object(C,'absorb_stray_char',side_effect=lambda text,a,b,value:(a,b)):
            return C._check_replacement(source,(start,end,changed,'IT・PC操作'),None,None,
                halfwidth_taken=((start,end),))

    def test_exact_original_key_repeat_inside_replacement(self):
        for raw,kana in (('gakuseihahanashimasu','がくせいははなします'),
                         ('gakuseihahanashimasen','がくせいははなしません'),
                         ('haha','はは'),('ｈａｈａ','はは'),('syasyasya','しゃしゃしゃ')):
            with self.subTest(raw=raw):
                self.assertTrue(C._literal_romaji_repetition(raw,kana))
                self.assertEqual(self.check(raw,0,len(raw),kana)[1],'accepted')

    def test_missing_or_changed_keys_cannot_claim_original_repeat(self):
        for raw,kana in (('gakuseihanashimasu','がくせいははなします'),
                         ('gakuseikahanashimasu','がくせいははなします'),
                         ('hahaha','はははは'),('がくせいはなします','がくせいははなします')):
            with self.subTest(raw=raw):
                self.assertFalse(C._literal_romaji_repetition(raw,kana))
                self.assertEqual(self.check(raw,0,len(raw),kana),(None,'new_repetition'))

    def test_exact_restore_does_not_excuse_an_untouched_neighbor_seam(self):
        for raw,a,b,kana in (('はha',1,3,'は'),('haは',0,2,'は'),
                            ('はhaha',1,5,'はは'),('hahaは',0,4,'はは')):
            with self.subTest(raw=raw):
                self.assertEqual(self.check(raw,a,b,kana),(None,'new_repetition'))

    def test_non_romaji_or_written_spelling_is_not_literal_key_proof(self):
        for raw,kana in (('がくせいははなします','学生は話します'),('ha ha','はは'),
                         ('ha2ha','はは'),('haha','母'),('h.a.h.a','はは')):
            self.assertFalse(C._literal_romaji_repetition(raw,kana))

    def test_user_stop_still_precedes_original_key_proof(self):
        from unittest.mock import Mock
        stop=Mock();stop.blocks.return_value=True
        self.assertEqual(C._check_replacement('gakuseihahanashimasu',
            (0,20,'がくせいははなします','IT・PC操作'),None,None,
            decisions=stop,halfwidth_taken=((0,20),)),(None,'user_block'))


if __name__=='__main__':unittest.main()
