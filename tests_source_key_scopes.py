# -*- coding: utf-8 -*-
"""Unchanged kanji padding cannot hide an original physical deletion."""
import unittest
from unittest.mock import patch
import corrector as C
import contextual_repair as Q
import reading_likelihood as L
from tests_analysis_async import initial


class SourceKeyScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial()
        cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def check(self,text,start,end,surface):
        return C._check_replacement(text,(start,end,surface,'かな入力'),self.a.store,
            self.tok,self.a.dict_index,conv_taken=((start,end),))

    def test_unchanged_padding_cannot_hide_nonadjacent_deletions(self):
        for char in ('あ','こ'):
            text='他の行と'+char+'同じです。'
            for start,end,new in ((4,5,''),(0,len(text),'他の行と同じです。')):
                with self.subTest(char=char,end=end):
                    self.assertEqual(self.check(text,start,end,new),
                        (None,'nonadjacent_original_key_deletion'))
            target=Q.RepairTarget(text,0,len(text),0,len(text),(),False,'')
            self.assertEqual(Q.validate(target,'他の行と同じです。',C,self.tok,
                self.a.store,self.a.dict_index),(False,'nonadjacent_original_key_deletion'))

    def test_native_role_supplies_the_actual_adjacent_reading(self):
        text='他の行とえ同じです。';tokens=self.tok(text)
        self.assertEqual(L.adjacent_readings(text,tokens,4,5),('と',''))
        self.assertEqual(L.adjacent_readings(text,tokens,4,5,native_boundaries=True),('と','おな'))
        for start,end,new in ((4,5,''),(0,len(text),'他の行と同じです。')):
            with self.subTest(end=end):
                candidate,reason=self.check(text,start,end,new)
                self.assertIsNotNone(candidate,reason)
        # Passing a candidate does not invent a source anomaly or automatic repair.

    def test_padded_kana_and_kanji_outputs_share_original_key_proof(self):
        # This source has a real remote intrusion, not 文字's attested もんじ reading.
        typed='もじにゅこうりょく';text='文字は'+typed+'です。'
        for target in ('もじにゅうりょく','文字入力'):
            for start,end,new in ((3,3+len(typed),target),
                                  (0,len(text),'文字は'+target+'です。')):
                with self.subTest(target=target,end=end):
                    self.assertTrue(C._nonadjacent_drop_in_source(text,start,end,new,self.tok))
                    self.assertEqual(self.check(text,start,end,new),
                        (None,'nonadjacent_original_key_deletion'))

    def test_recursive_source_and_separate_deletions_use_original_neighbors(self):
        text='甲もんてだい乙'
        token=C._CORRECTION_PATH.set(('甲もんせだい乙',text))
        try:
            self.assertTrue(C._nonadjacent_drop_in_source(text,0,len(text),'甲もんだい乙',self.tok))
        finally:C._CORRECTION_PATH.reset(token)
        text='他の行とえ同じです。次の行とあ同じです。'
        target='他の行と同じです。次の行と同じです。'
        self.assertTrue(C._nonadjacent_drop_in_source(text,0,len(text),target,self.tok))

    def test_transposition_punctuation_and_duplicate_keys_keep_distinct_policies(self):
        for text,target in (('甲あい乙','甲いあ乙'),('甲あ、い乙','甲あい乙')):
            with self.subTest(text=text):
                self.assertFalse(C._nonadjacent_drop_in_source(text,0,len(text),target,self.tok))
        text='甲かか乙'
        with patch('vocabulary.dup_repair_enabled',return_value=False):
            self.assertTrue(C._repeat_repair_disabled_in_source(text,0,len(text),'甲か乙',self.tok))

    def test_native_role_ambiguity_and_unreadable_words_still_supply_no_keys(self):
        text='え行';tokens=self.tok(text)
        self.assertEqual(L.adjacent_readings(text,tokens,0,1,native_boundaries=True),('',''))
        with patch('kanji_guess.ime_readings_for',side_effect=lambda s:['ぎょう'] if s=='行' else []):
            self.assertEqual(L.adjacent_readings(text,tokens,0,1,native_boundaries=True),('','ぎょ'))
        tokens=[('え','フィラー','え',0,1,True,''),('蒟','名詞:一般','',1,2,False,'')]
        self.assertEqual(L.adjacent_readings('え蒟',tokens,0,1,native_boundaries=True),('',''))

    def test_joined_native_word_constrains_the_same_written_neighbors(self):
        text='画゜像を保存します。';tokens=self.tok(text)
        self.assertEqual(L.adjacent_readings(text,tokens,1,2,native_boundaries=True),('','ぞう'))
        self.assertEqual(L.native_joined_word_neighbors(text,tokens,1,2),('が','ぞう'))
        for start,end,new in ((1,2,''),(0,3,'画像'),(0,len(text),'画像を保存します。')):
            with self.subTest(end=end):
                candidate,reason=self.check(text,start,end,new)
                self.assertIsNotNone(candidate,reason)
        with patch('kanji_guess.ime_readings_for',side_effect=lambda s:['え'] if s=='画' else []):
            self.assertEqual(L.native_joined_word_neighbors(text,tokens,1,2),('',''))
        self.assertEqual(L.native_joined_word_neighbors('え行',self.tok('え行'),0,1),('',''))
        invented=[('蒟','名詞:一般','',0,1,False,''),('゜','記号:一般','゜',1,2,True,''),
                  ('像','名詞:接尾:一般','ぞう',2,3,True,'')]
        self.assertEqual(L.native_joined_word_neighbors('蒟゜像',invented,1,2),('',''))

    def test_unavailable_native_analyzer_keeps_attested_fallback_readings(self):
        token=('該当','名詞:一般','がいとう',0,2,True,'')
        with patch('morphology.HAS_JANOME',False), patch('morphology.dictionary_inflections') as native:
            self.assertEqual(L._options(token,native_boundaries=True),
                             (('がいとう',),'analyzed_word_boundary'))
            self.assertEqual(L._options(('蒟','名詞:一般','',0,1,False,''),native_boundaries=True),
                             ((),'unreadable'))
            native.assert_not_called()

    def test_romaji_does_not_borrow_the_kana_keyboard_rule(self):
        text='他の行とあ同じです。'
        token=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            self.assertFalse(C._nonadjacent_drop_in_source(text,0,len(text),'他の行と同じです。',self.tok))
        finally:C._CORRECTION_INPUT_METHOD.reset(token)


if __name__=='__main__':unittest.main()
