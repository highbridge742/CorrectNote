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

    def test_native_okurigana_edge_keeps_original_neighbor_keys(self):
        text='本を貸すしました';tokens=self.tok(text)
        self.assertEqual(L.adjacent_readings(text,tokens,3,4),('','しま'))
        self.assertEqual(L.adjacent_readings(text,tokens,3,4,native_boundaries=True),('か','しま'))
        for start,end,new in ((3,4,''),(2,5,'貸し'),(2,8,'貸しました')):
            with self.subTest(span=(start,end)):
                self.assertIn(('かすし','かし'),list(C._source_kana_deletion_pairs(text,start,end,new,self.tok)))
                self.assertFalse(C._nonadjacent_drop_in_source(text,start,end,new,self.tok))
                candidate,reason=self.check(text,start,end,new)
                self.assertIsNotNone(candidate,reason)
        # The same original source is still used after an intermediate kana repair.
        context=C._CORRECTION_PATH.set((text,'本をかしました'))
        try:
            self.assertFalse(C._nonadjacent_drop_in_source('本をかしました',2,4,'貸し',self.tok))
        finally:C._CORRECTION_PATH.reset(context)

    def test_okurigana_evidence_preserves_unknowns_ambiguity_and_remote_keys(self):
        text='本を貸すしました';tokens=self.tok(text)
        self.assertEqual(L._native_okurigana_before(text,tokens,2),'')
        self.assertEqual(L._native_okurigana_before(text,tokens,4),'')
        changed=[tuple((*t[:5],False,*t[6:])) if t[0]=='貸す' else t for t in tokens]
        self.assertEqual(L._native_okurigana_before(text,changed,3),'')
        with patch.object(L,'_options',return_value=(('かす','けす'),'native_word_boundary')):
            self.assertEqual(L._native_okurigana_before(text,tokens,3),'')
        with patch('kanji_guess.ime_readings_for',side_effect=lambda word:['かし'] if word=='貸す' else []):
            self.assertEqual(L._native_okurigana_before(text,tokens,3),'')
        for source,target in (('消すしました','消しました'),('増すしました','増しました')):
            with self.subTest(source=source):
                self.assertTrue(C._nonadjacent_drop_in_source(source,0,len(source),target,self.tok))
        with patch('vocabulary.dup_repair_enabled',return_value=False):
            self.assertTrue(C._repeat_repair_disabled_in_source('貸すすしました',0,7,'貸すしました',self.tok))

    def test_written_intrusion_finishes_with_original_keys_and_shared_gate(self):
        import app
        from last_choice import set_active
        try:
            source='本を貸すしました';a=initial()
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'本を貸しました')
            self.assertEqual(r['odd_spans'],[])
            self.assertEqual(r['analysis_status'],'complete')
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
        finally:set_active(None)

    def test_new_diagonal_exclusion_is_not_an_adjacent_substitution(self):
        import kana_layout as K
        self.assertGreater(K.kana_key_distance('ん','ま'),1.0)
        self.assertFalse(any(row.reading=='よみます' and row.operation=='adjacent_substitution'
                             for row in Q.key_repairs('よみんす')))
        self.assertFalse(any(row.reading=='よみます' and row.operation=='nonadjacent_substitution'
                            for row in Q.nonadjacent_key_repairs('よみんす')))

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

    def test_joined_rendaku_supplies_keys_only_at_attested_source_edges(self):
        with patch('ime_language._factory',None):
            for source,span,pair,target in (
                    ('平ん仮名',(1,2),('ひら','がな'),'平仮名'),
                    ('花ん火',(1,2),('はな','び'),'花火')):
                with self.subTest(source=source):
                    self.assertEqual(L.native_joined_word_neighbors(source,self.tok(source),*span),pair)
                    candidate,reason=self.check(source,0,len(source),target)
                    self.assertIsNotNone(candidate,reason)
            # 青ん is an actual inflected verb; its internal ん is not
            # an independently bounded intrusion between two source nouns.
            self.assertEqual(L.native_joined_word_neighbors('青ん空',self.tok('青ん空'),1,2),('',''))
            # Rendaku is a word reading, not permission to delete a remote key.
            source='紙ん袋'
            self.assertEqual(L.native_joined_word_neighbors(source,self.tok(source),1,2),('かみ','ぶく'))
            self.assertEqual(self.check(source,0,len(source),'紙袋'),
                             (None,'nonadjacent_original_key_deletion'))
            with patch('kanji_guess.ime_readings_for',side_effect=lambda s:['かな'] if s=='仮名' else []):
                self.assertEqual(L.native_joined_word_neighbors('平ん仮名',self.tok('平ん仮名'),1,2),('',''))

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

    def test_excluded_diagonals_are_not_intrusion_or_substitution_proof(self):
        import kana_layout as K
        for bad,good in (('ほきん','ほん'),('きすり','きり'),('まきす','ます'),
                         ('でしあた','でした'),('ちいちさく','ちいさく'),
                         ('はさまして','さまして'),('資料を゜保存','資料を保存')):
            with self.subTest(source=bad):self.assertIs(K.single_key_drop_adjacency(bad,good),False)
        for left,right in (('え','い'),('せ','り'),('の','る'),('ま','ん')):
            with self.subTest(keys=(left,right)):self.assertGreater(K._base_distance(left,right),1.0)


    def test_retired_legacy_targets_have_no_neighbor_key_proof(self):
        import kana_layout as K
        for bad,good in (('かたづけるて','かたづけて'),('まんど','まど'),
                         ('おくれ゛ました','おくれました')):
            with self.subTest(source=bad):self.assertIs(K.single_key_drop_adjacency(bad,good),False)
        for left,right in (('は','さ'),('つ','し'),('い','は')):
            with self.subTest(keys=(left,right)):self.assertGreater(K._base_distance(left,right),1.0)


if __name__=='__main__':unittest.main()
