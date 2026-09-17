# -*- coding: utf-8 -*-
"""Uncomposable input keys remain evidence, never valid candidate readings."""
import os
import unittest
from unittest.mock import patch
import mark_usage as U
import contextual_repair as R


def token(surface,reading,pos,start,known=True):
    return (surface,pos,reading,start,start+len(surface),known,'')


class UnattachedMarkTests(unittest.TestCase):
    def setUp(self):
        U.unattached_positions.cache_clear()

    def tearDown(self):
        U.unattached_positions.cache_clear()

    def test_attachment_is_asked_of_the_existing_normalizer(self):
        for line,positions in (('ン゛像を保存',(1,)),('科゜像を保存',(1,)),
                               ('文字゛列を選ぶ',(2,)),('し゛るしを読む',()),
                               ('は゜んを読む',()),('か\u3099ぞうを読む',()),
                               ('こ゜を読む',())):
            self.assertEqual(U.unattached_positions(line),positions,line)

    def test_numeric_marks_separators_and_explicit_notation_are_not_words(self):
        for line in ('37゜の角度','北緯35゜です','@ ⇒ ゛','[ ⇒ ゜','゛説明',
                     '記号は゛です','「画゜像」という誤入力','「画゜像」と入力した',
                     'あ゛ー！','声は「う゛う゛」でした','文字列（゛付き）'):
            self.assertEqual(U.unattached_positions(line),(),line)

    def test_word_internal_mark_does_not_split_the_original_target(self):
        text='ン゛像を保存'
        parts=[token('ン','ん','名詞:一般',0,False),token('゛','゛','記号:一般',1),
               token('像','ぞう','名詞:接尾:一般',2),token('を','を','助詞:格助詞',3),
               token('保存','ほぞん','名詞:サ変接続',4)]
        with patch('oddness.is_odd_run',return_value=[('ン','゛',0,2)]):
            rows=R.targets_for_line(text,lambda _:parts,None,None)
        self.assertEqual([(r.start,r.end,r.text,r.following) for r in rows],[(0,3,'ン゛像','を保存')])
        with patch('oddness.is_odd_run',return_value=[]):
            self.assertEqual(R.targets_for_line(text,lambda _:parts,None,None),[])

    def test_all_kana_mark_target_uses_the_same_anomaly_contract(self):
        text='もじ゛つを選ぶ'
        parts=[token('もじ','もじ','名詞:一般',0),token('゛','゛','記号:一般',2),
               token('つ','つ','名詞:一般',3),token('を','を','助詞:格助詞',4),
               token('選ぶ','えらぶ','動詞:自立',5)]
        with patch('oddness.is_odd_run',return_value=[('じ','゛',1,3)]):
            rows=R.targets_for_line(text,lambda _:parts,None,None)
        self.assertEqual([r.text for r in rows],['もじ゛つ'])

    def test_original_mark_segment_reaches_the_input_reading(self):
        text='ン゛像'
        parts=[token('ン','ん','名詞:一般',0,False),token('゛','゛','記号:一般',1),
               token('像','ぞう','名詞:接尾:一般',2)]
        target=R.RepairTarget(text,0,3,0,3,(('ン','゛',0,2),),True,'')
        with patch('kanji_guess.ime_readings_for',return_value=[]), \
             patch('inflected_lexicon.dictionary_readings',return_value=()), \
             patch('kanji_guess.reading_combos_with_evidence',return_value=[]):
            rows=R.reading_evidence(target,lambda _:parts,None)
        self.assertEqual(rows[0].text,'ん゛ぞう')
        self.assertEqual(rows[0].segments[1],(1,2,'゛','literal_mark_key'))

    def test_key_repair_produces_only_valid_phonetic_readings(self):
        self.assertTrue(R._is_input_reading('ん゛ぞう'))
        self.assertFalse(R._is_reading('ん゛ぞう'))
        rows=R.key_repairs('ん゛ぞう')
        self.assertTrue(rows)
        self.assertTrue(all(R._is_reading(r.reading) for r in rows))
        candidate=next(r for r in rows if r.reading=='がぞう')
        self.assertEqual((candidate.operation,candidate.pressed,candidate.intended),
                         ('adjacent_substitution','ん','か'))
        self.assertEqual(R._input_kana('ン\u3099像'),'ん゛像')

    def test_existing_mark_setting_and_duplicate_setting_still_apply(self):
        with patch.dict(os.environ,{'CN_MARK_SLIP':'1'}):
            self.assertIn('がぞう',[r.reading for r in R.key_repairs('か゜ぞう')])
        with patch.dict(os.environ,{'CN_MARK_SLIP':'0'}):
            self.assertNotIn('がぞう',[r.reading for r in R.key_repairs('か゜ぞう')])
        with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
            self.assertNotIn('もじれつ',[r.reading for r in R.key_repairs('もじ゛れつ')])
        with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
            self.assertIn('もじれつ',[r.reading for r in R.key_repairs('もじ゛れつ')])


    def normalization(self,source='を゛説明',changed='を説明',positions=(1,),
                      neighbors=('を','せ'),known=True,blocked=False,odd=False,complete=True):
        import corrector as C
        def tokenize(text):
            return [token(c,c,'名詞:一般',i,known) for i,c in enumerate(text)]
        with patch('reading_likelihood.adjacent_readings',return_value=neighbors), \
             patch.object(C,'_check_replacement',side_effect=lambda line,r,*a:
                          (None,'user_block') if blocked else (r,'accepted')), \
             patch('oddness.structural_anomaly_in_range',return_value=odd), \
             patch.object(U,'normalization_seam_is_complete',return_value=complete):
            return U.normalized_intrusions(source,changed,positions,tokenize)

    def test_proved_intrusion_can_be_the_normalization_repair_itself(self):
        self.assertTrue(self.normalization())
        self.assertTrue(self.normalization(source='を\u3099説明'))

    def test_distant_or_missing_neighbor_reading_does_not_license_deletion(self):
        for neighbors in (('い','に'),('','せ'),('を','')):
            self.assertFalse(self.normalization(neighbors=neighbors))

    def test_normalization_cannot_change_any_other_original_character(self):
        self.assertFalse(self.normalization(changed='を解説'))
        self.assertFalse(self.normalization(positions=()))

    def test_original_notation_and_outside_marks_are_not_intrusion_targets(self):
        for source,changed,positions in (('゛説明','説明',(0,)),
                ('記号は゛です','記号はです',(3,)),
                ('「を゛説明」は誤入力です。','「を説明」は誤入力です。',(2,))):
            self.assertFalse(self.normalization(source,changed,positions))

    def test_unknown_candidate_or_remaining_structural_error_keeps_evidence(self):
        self.assertFalse(self.normalization(known=False))
        self.assertFalse(self.normalization(odd=True))
        self.assertFalse(self.normalization(complete=False))

    def test_rejected_replacement_is_not_normalized_around_the_common_check(self):
        self.assertFalse(self.normalization(blocked=True))

    def test_repeated_mark_is_not_mislabelled_as_adjacent_intrusion(self):
        for setting in ('0','1'):
            with patch.dict(os.environ,{'CN_NO_DUP':setting}):
                self.assertFalse(self.normalization(source='で゛から',changed='でから',
                                                    neighbors=('で','か')))

    def test_each_dropped_mark_requires_its_own_physical_and_grammatical_proof(self):
        self.assertTrue(self.normalization(source='を゛整理を゛説明',changed='を整理を説明',positions=(1,5)))
        self.assertFalse(self.normalization(source='を゛整理 ゛説明',changed='を整理 説明',positions=(1,5)))


if __name__=='__main__':
    unittest.main()
