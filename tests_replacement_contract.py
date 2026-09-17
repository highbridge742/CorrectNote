# -*- coding: utf-8 -*-
"""最終検査が同じ候補・原文範囲について理由を返すことを確認する。"""
import unittest
from unittest.mock import patch, Mock
import corrector as C


class ReplacementContractTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(C, 'absorb_stray_char', side_effect=lambda line, a, b, value: (a, b)),
            patch.object(C, '_reading_spelled_in_bracket', return_value=False),
            patch.object(C, 'long_vowel_protected_span', return_value=None),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def check(self, original, corrected, **kwargs):
        return C._check_replacement(original, (0, len(original), corrected, 'その他'),
                                    None, None, **kwargs)

    def test_unchanged_is_not_a_replacement(self):
        self.assertEqual(self.check('文章', '文章'), (None, 'unchanged'))

    def test_user_block_is_distinct_from_structural_failure(self):
        decision = Mock()
        decision.blocks.return_value = True
        self.assertEqual(self.check('誤字', '文字', decisions=decision), (None, 'user_block'))
        decision.blocks.assert_called_once_with('誤字', '文字')

    def test_length_and_existing_exemptions(self):
        self.assertEqual(self.check('あいうえお', '字'), (None, 'length_delta'))
        accepted, reason = self.check('あいうえお', '字', lu_taken=[(0, 5)], conv_taken=[])
        self.assertEqual(accepted, (0, 5, '字', 'その他'))
        self.assertEqual(reason, 'accepted')

    def test_new_repetition_is_rejected(self):
        self.assertEqual(self.check('かがみ', 'かかみ'), (None, 'new_repetition'))

    def test_particle_insertion_is_not_a_repetition(self):
        self.assertEqual(C._check_replacement('静か歩く',(2,2,'に','かな入力'),None,None),
                         ((2,2,'に','かな入力'),'accepted'))
        self.assertFalse(C._has_new_repetition('','に'))
        self.assertTrue(C._has_new_repetition('','にに'))

    def test_inserted_particle_uses_original_neighbors(self):
        for line,point in (('静かに歩く',2),('静かに歩く',3)):
            with self.subTest(point=point):
                self.assertEqual(C._check_replacement(line,(point,point,'に','かな入力'),None,None),
                                 (None,'new_repetition'))

    def test_partial_replacement_cannot_duplicate_untouched_ending(self):
        self.assertEqual(C._check_replacement('しますえか',(3,4,'か','かな入力'),None,None),
                         (None,'new_repetition'))
        self.assertEqual(C._check_replacement('にわ',(1,2,'に','かな入力'),None,None),
                         (None,'new_repetition'))

    def test_repeated_glyphs_across_actual_attributive_boundary(self):
        def native(text):
            return [('し','動詞:自立','し',0,1,True,'連用形'),
                    ('た','助動詞','た',1,2,True,'基本形'),
                    ('ため','名詞:非自立:副詞可能','ため',2,4,True,'')]
        with patch('contextual_repair._completed_predicate_token',return_value=True):
            self.assertEqual(C._check_replacement('しなため',(1,2,'た','かな入力'),None,native),
                             ((1,2,'た','かな入力'),'accepted'))
        self.assertFalse(C._repeated_nominal_seam('かか',1,lambda _: [
            ('か','助詞:終助詞','か',0,1,True,''),('か','助詞:終助詞','か',1,2,True,'')]))

    def test_punctuation_boundary_and_symbol_exception(self):
        out = C._check_replacement('め。', (0, 1, '。', '記号'), None, None)
        self.assertEqual(out, (None, 'new_punctuation'))
        out = C._check_replacement('めめ', (0, 2, '？？', '記号'), None, None)
        self.assertEqual(out, ((0, 2, '？？', '記号'), 'accepted'))

    def test_absorbed_span_is_the_returned_span(self):
        with patch.object(C, 'absorb_stray_char', return_value=(0, 3)):
            out = C._check_replacement('あいう', (0, 2, '文字', 'その他'), None, None)
        self.assertEqual(out, ((0, 3, '文字', 'その他'), 'accepted'))

    def test_remote_deletion_is_rejected_at_the_shared_final_gate(self):
        self.assertEqual(self.check('もんせだい','もんだい'),
                         (None,'nonadjacent_original_key_deletion'))
        self.assertEqual(self.check('もとし','もと')[1],'accepted')

    def test_single_character_drop_uses_the_original_neighbor(self):
        self.assertEqual(C._check_replacement('もとし',(2,3,'','その他'),None,None),
                         ((2,3,'','その他'),'accepted'))

    def test_recursive_preparation_cannot_make_a_remote_key_adjacent(self):
        token=C._CORRECTION_PATH.set(('もんせだい','もんてだい'))
        try:
            self.assertEqual(self.check('もんてだい','もんだい'),
                             (None,'nonadjacent_original_key_deletion'))
        finally:C._CORRECTION_PATH.reset(token)

    def test_kana_key_deletion_policy_does_not_replace_romaji_geometry(self):
        token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:self.assertEqual(self.check('もんせだい','もんだい')[1],'accepted')
        finally:C._CORRECTION_INPUT_METHOD.reset(token)

    def test_kanji_candidate_retains_its_actual_reading_for_physical_proof(self):
        def native(text):return [(text,'名詞:一般','もんだい',0,len(text),True,'')]
        self.assertEqual(C._check_replacement('もんせだい',(0,5,'問題','かな入力'),None,native),
                         (None,'nonadjacent_original_key_deletion'))

    def test_punctuation_and_same_length_voicing_are_different_operations(self):
        from kana_layout import single_key_drop_adjacency
        self.assertIsNone(single_key_drop_adjacency('あ、','あ'))
        self.assertIsNone(single_key_drop_adjacency('が','か'))

    def test_reading_annotation_and_long_vowel_have_distinct_reasons(self):
        with patch.object(C, '_reading_spelled_in_bracket', return_value=True):
            self.assertEqual(self.check('よみ', '読み'), (None, 'reading_annotation'))
        with patch.object(C, 'long_vowel_protected_span', return_value='same word'):
            self.assertEqual(self.check('よみ', '読み'), (None, 'long_vowel'))

if __name__ == '__main__':
    unittest.main()
