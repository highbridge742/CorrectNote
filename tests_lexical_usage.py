# -*- coding: utf-8 -*-
"""AI usage judgments guide choices without treating missing coverage as evidence."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import candidates as A
import corrector as C
import kango_tier as K
import morphology as M
import reading_segments as R


class LexicalUsageTests(unittest.TestCase):
    def tearDown(self):
        import literal_examples as L
        L.named_identifier_parts.cache_clear()
        L.native_reading_gloss_ranges.cache_clear()
        R._native_nominal_reading_faces.cache_clear()
        K._explicit_reading_faces.cache_clear()
        K.reading_is_explicitly_restricted.cache_clear()

    def test_named_identifiers_require_a_native_noun_and_actual_right_boundary(self):
        import literal_examples as L
        tokens=[M.Token('資料','名詞','資料','しりょう',0,2,True,'一般',''),
                M.Token('DD','名詞','DD','DD',2,4,False,'一般',''),
                M.Token('を','助詞','を','を',4,5,True,'格助詞:一般','')]
        forms=(('名詞,一般,*,*','*','資料','しりょう'),)
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',side_effect=lambda s:forms if s=='資料' else ()):
            self.assertEqual(L.named_identifier_ranges('資料DDを'),[(0,4)])
            self.assertEqual(L.named_identifier_ranges('資料ＤＤを'),[(0,4)])
            self.assertEqual(L.named_identifier_ranges('資料DD'),[(0,4)])
            self.assertEqual(L.named_identifier_ranges('資料ddを'),[])
            tokens[-1]=M.Token('カ','名詞','カ','か',4,5,True,'一般','')
            self.assertEqual(L.named_identifier_ranges('資料DDカ'),[])
        L.named_identifier_parts.cache_clear()
        with patch.object(M,'tokenize',return_value=tokens), \
             patch.object(M,'dictionary_inflections',return_value=()):
            self.assertEqual(L.named_identifier_ranges('資料DD'),[])

    def test_reading_annotation_must_match_the_actual_preceding_native_reading(self):
        import literal_examples as L
        tokens=[M.Token('法則','名詞','法則','ほうそく',0,2,True,'一般','')]
        with patch.object(M,'tokenize',return_value=tokens):
            self.assertEqual(L.native_reading_gloss_ranges('法則（ほうそく、law）'),[(3,7)])
            self.assertEqual(L.native_reading_gloss_ranges('法則（ほうしん）'),[])
            self.assertEqual(L.native_reading_gloss_ranges('法則（ほうそく)'),[])
            self.assertEqual(L.native_reading_gloss_ranges('法則(ほうそく、law)'),[(3,7)])
            self.assertEqual(L.native_reading_gloss_ranges('法則（しゅくふ）'),[])
            self.assertEqual(L.native_reading_gloss_ranges('ああ（ほうそく）'),[])
        L.native_reading_gloss_ranges.cache_clear()
        tokens[0]=M.Token('法則','名詞','法則','ほうそく',0,2,False,'一般','')
        with patch.object(M,'tokenize',return_value=tokens):
            self.assertEqual(L.native_reading_gloss_ranges('法則（ほうそく、law）'),[])

    def test_gloss_unknown_kana_name_has_its_literal_reading_but_unknown_kanji_does_not(self):
        import literal_examples as L
        tokens=[M.Token('ミップ','名詞','ミップ','ミップ',0,3,False,'一般',''),
                M.Token('の','助詞','の','の',3,4,True,'連体化',''),
                M.Token('規則','名詞','規則','きそく',4,6,True,'一般','')]
        with patch.object(M,'tokenize',return_value=tokens):
            self.assertEqual(L.native_reading_gloss_ranges('ミップの規則（みっぷのきそく、rule）'),[(7,14)])
            self.assertEqual(L.native_reading_gloss_ranges('ミップの規則（みっぷのきそつ）'),[])
        L.native_reading_gloss_ranges.cache_clear()
        tokens[0]=M.Token('未詳名','名詞','未詳名','ミップ',0,3,False,'一般','')
        with patch.object(M,'tokenize',return_value=tokens):
            self.assertEqual(L.native_reading_gloss_ranges('未詳名の規則（みっぷのきそく）'),[])

    def test_written_coordinate_categories_are_complete_and_readings_are_not_invented(self):
        from semantic_roles import is_nominal_coordination
        for word in ('性数格','人称数','人称性数格','時制相法'):
            self.assertTrue(is_nominal_coordination(word),word)
            self.assertTrue(C._chunk_is_intact(word,None),word)
            self.assertTrue(C._d42_known_unit(word,None),word)
        for word in ('性数角','せいすうかく','性性数','性数格誤','性'):
            self.assertFalse(is_nominal_coordination(word),word)

    def test_missing_classification_is_distinct_from_an_explicit_restricted_judgment(self):
        self.assertEqual(K.known_usage_tier('按針'),3)
        self.assertEqual(K.known_usage_tier('工房'),1)
        self.assertEqual(K.known_usage_tier('古文'),2)
        self.assertIsNone(K.known_usage_tier('未分類の試験用語'))
        self.assertFalse(K.is_restricted('未分類の試験用語'))
        self.assertEqual(C._kango_tier_of('委員会'),1)

    def test_existing_semantic_nouns_supply_ordinary_evidence_without_a_second_roster(self):
        from semantic_roles import NOUN_ROLES
        self.assertIn('人',NOUN_ROLES)
        self.assertIn(K.known_usage_tier('人'),(1,2))

    def test_restricted_candidates_remain_selectable_and_kind_order_is_preserved(self):
        rows=[dict(surface='宣旨',kind='homophone'),dict(surface='戦時',kind='homophone'),
              dict(surface='未分類の試験用語',kind='homophone'),dict(surface='工房',kind='typo')]
        original={id(row) for row in rows}
        A._prefer_ordinary_usage(rows)
        self.assertEqual([r['surface'] for r in rows],['戦時','未分類の試験用語','宣旨','工房'])
        self.assertEqual({id(row) for row in rows},original)

    def test_single_word_menu_keeps_explicit_choice_before_ai_usage(self):
        rows=[dict(surface='戦時',reading='せんじ',kind='homophone'),
              dict(surface='宣旨',reading='せんじ',kind='homophone'),
              dict(surface='工房',reading='こうぼう',kind='typo')]
        with patch('last_choice.surface_for_reading',side_effect=lambda r:'宣旨' if r=='せんじ' else None):
            A._prefer_ordinary_usage(rows)
        self.assertEqual([r['surface'] for r in rows],['宣旨','戦時','工房'])
        self.assertEqual(A._explicit_choice_rank(dict(surface='宣旨')),1)

    def range_candidates(self,chosen=None):
        rows=[dict(surface='宣旨',reading='せんじ',kind='homophone'),
              dict(surface='戦時',reading='せんじ',kind='homophone')]
        with patch.object(A,'build_candidates',return_value=rows), \
             patch('last_choice.surface_for_reading',return_value=chosen):
            return A.build_range_candidates([('せんじ','せんじ')],object(),lambda *a,**k:[])

    def test_range_candidates_apply_the_same_usage_judgment(self):
        self.assertEqual(self.range_candidates()[0]['surface'],'戦時')

    def test_last_explicit_choice_overrides_the_generic_usage_order(self):
        self.assertEqual(self.range_candidates('宣旨')[0]['surface'],'宣旨')

    def test_a_native_rare_noun_does_not_certify_an_ordinary_kana_reading(self):
        entries={'故実':(('名詞,一般,*,*','*','故実','こじつ'),),
                 '工房':(('名詞,一般,*,*','*','工房','こうぼう'),)}
        with patch.object(C,'table_surfaces_for_reading',side_effect=lambda rd,limit:
                {'こじつ':['故実'],'こうぼう':['工房']}.get(rd,[])), \
             patch.object(M,'dictionary_inflections',side_effect=lambda word:entries.get(word,())):
            R._native_nominal_reading_faces.cache_clear()
            self.assertEqual(R._native_nominal_reading_faces('こじつ'),())
            self.assertEqual(R._native_nominal_reading_faces('こうぼう'),('工房',))

    def test_reading_usage_does_not_demote_the_ordinary_spelling_or_daily_reading(self):
        self.assertEqual(K.known_usage_tier('叔父'),1)
        self.assertEqual(K.usage_tier_for_reading('叔父','おじ'),1)
        self.assertEqual(K.usage_tier_for_reading('叔父','しゅくふ'),3)
        rows=[dict(surface='叔父',reading='しゅくふ',kind='typo'),
              dict(surface='修復',reading='しゅうふく',kind='typo')]
        A._prefer_ordinary_usage(rows)
        self.assertEqual(rows[0]['surface'],'修復')
        self.assertEqual(len(rows),2)

    def test_native_compound_case_closes_a_complete_ordinary_noun_reading(self):
        tokens=[('しゅう','名詞:一般','しゅう',0,3,True,'*'),
                ('ふく','名詞:一般','ふく',3,5,True,'*'),
                ('について','助詞:格助詞:連語','について',5,9,True,'*')]
        entries={'について':(('助詞,格助詞,連語,*','*','について','について'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda word:entries.get(word,())), \
             patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:('修復',) if rd=='しゅうふく' else ()):
            self.assertTrue(R.native_nominal_reading_context('しゅうふくについて',0,9,lambda _:tokens))
            self.assertFalse(R.native_nominal_reading_context('しゅうふくについて',0,4,lambda _:tokens))
            self.assertFalse(R.native_nominal_reading_context('しゅうふくについて',0,9,lambda _:tokens,require_predicate=True))
            tokens[-1]=('について','名詞:一般','について',5,9,True,'*')
            self.assertFalse(R.native_nominal_reading_context('しゅうふくについて',0,9,lambda _:tokens))

    def test_native_usage_roster_does_not_depend_on_the_cost_table(self):
        forms=(('名詞,一般,*,*','*','店','みせ'),)
        with patch.object(C,'table_surfaces_for_reading',return_value=[]), \
             patch.object(K,'_explicit_reading_faces',return_value={'みせ':{'店'}}), \
             patch.object(M,'dictionary_inflections',side_effect=lambda s:forms if s=='店' else ()):
            R._native_nominal_reading_faces.cache_clear()
            self.assertEqual(R._native_nominal_reading_faces('みせ'),('店',))
            self.assertEqual(R._native_nominal_reading_faces('べつよみ'),())

    def test_nominal_case_fragment_is_not_a_completed_predicate(self):
        tokens=[('しりょう','名詞:一般','しりょう',0,4,True,'*'),
                ('を','助詞:格助詞:一般','を',4,5,True,'*')]
        entries={'を':(('助詞,格助詞,一般,*','*','を','を'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda word:entries.get(word,())), \
             patch.object(R,'_native_nominal_reading_faces',return_value=('資料',)):
            self.assertTrue(R.native_nominal_reading_context('しりょうを',0,5,lambda _:tokens))
            self.assertFalse(R.native_nominal_reading_context('しりょうを',0,5,lambda _:tokens,require_predicate=True))

    def test_dialectal_n_particle_is_not_a_new_standard_nominal_boundary(self):
        tokens=[('りかん','名詞:一般','りかん',0,3,True,'*'),
                ('ん','助詞:格助詞:一般','ん',3,4,True,'*')]
        with patch.object(M,'dictionary_inflections',return_value=(('助詞,格助詞,一般,*','*','ん','ん'),)), \
             patch.object(R,'_native_nominal_reading_faces',return_value=('罹患',)):
            self.assertFalse(R.native_nominal_reading_context('りかんん',0,4,lambda _:tokens))

    def test_only_an_actual_genitive_with_a_native_following_noun_closes_the_reading(self):
        tokens=[('じしょう','名詞:一般','じしょう',0,4,True,'*'),
                ('の','助詞:連体化','の',4,5,True,'*'),
                ('原因','名詞:一般','げんいん',5,7,True,'*')]
        entries={'原因':(('名詞,一般,*,*','*','原因','げんいん'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda word:entries.get(word,())), \
             patch.object(R,'_native_nominal_reading_faces',return_value=('事象',)):
            self.assertTrue(R.native_nominal_reading_context('じしょうの原因',0,5,lambda _:tokens))
            self.assertFalse(R.native_nominal_reading_context('じしょうの原因',0,5,lambda _:tokens,require_predicate=True))
            self.assertFalse(R.native_nominal_reading_context('じしょうの',0,5,lambda _:tokens[:2]))
            tokens[1]=('の','名詞:非自立','の',4,5,True,'*')
            self.assertFalse(R.native_nominal_reading_context('じしょうの原因',0,5,lambda _:tokens))

    def test_ordinary_spelling_uses_exact_native_reading_and_respects_explicit_choice(self):
        entries={'林間':(('名詞,一般,*,*','*','林間','りんかん'),),
                 '林冠':(('名詞,一般,*,*','*','林冠','りんかん'),)}
        with patch.object(C,'table_surfaces_for_reading',return_value=['林冠','林間']), \
             patch.object(M,'dictionary_inflections',side_effect=lambda word:entries.get(word,())), \
             patch('last_choice.surface_for_reading',return_value=None):
            self.assertEqual(K.prefer_ordinary_spelling('りんかん','輪姦'),'林間')
            self.assertEqual(K.prefer_ordinary_spelling('別の読み','輪姦'),'輪姦')
            self.assertEqual(K.prefer_ordinary_spelling('りんかん','未評価表記'),'未評価表記')
            self.assertEqual(K.prefer_ordinary_spelling('りんかん','林間'),'林間')
        with patch('last_choice.surface_for_reading',return_value='輪姦'):
            self.assertEqual(K.prefer_ordinary_spelling('りんかん','輪姦'),'輪姦')

    def test_predicate_spelling_requires_a_complete_native_connection(self):
        import contextual_repair as CR
        with patch.object(M,'dictionary_inflections',side_effect=lambda s:(s,)), \
             patch.object(C,'table_surfaces_for_reading',return_value=['生理','整理']), \
             patch.object(CR,'_allows_grammatical_tail',side_effect=lambda forms,tail,rd,sf:
                 sf=='整理' and rd=='せいり' and tail=='してください'), \
             patch.object(CR,'_productive_predicate',return_value=True), \
             patch('last_choice.surface_for_reading',return_value=None):
            self.assertEqual(K.prefer_predicate_spelling('せいり','生理','してください'),'整理')
            self.assertEqual(K.prefer_predicate_spelling('せいり','生理','について'),'生理')
            self.assertEqual(K.prefer_predicate_spelling('せいり','生理','してん'),'生理')
            self.assertEqual(K.prefer_predicate_spelling('せいり','整理','してください'),'整理')
            self.assertEqual(K.prefer_predicate_spelling('別の読み','生理','してください'),'生理')
        with patch('last_choice.surface_for_reading',return_value='生理'):
            self.assertEqual(K.prefer_predicate_spelling('せいり','生理','してください'),'生理')

    def test_request_auxiliary_uses_native_role_after_te_only(self):
        import pos_grammar as P
        forms=(('動詞,非自立,*,*','命令ｉ','くださる','ください'),)
        with patch.object(M,'dictionary_inflections',side_effect=lambda s:forms if s=='ください' else ()):
            self.assertTrue(P.explain_kana_run('てください',initial_state='R',no_words=True))
            self.assertTrue(P.explain_kana_run('てくださいね',initial_state='R',no_words=True))
            self.assertFalse(P.explain_kana_run('ください',initial_state='R',no_words=True))
            self.assertFalse(P.explain_kana_run('てくださいです',initial_state='R',no_words=True))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(P.explain_kana_run('てください',initial_state='R',no_words=True))

    def test_multiple_ordinary_index_faces_are_ranked_instead_of_discarded(self):
        store=SimpleNamespace(lookup=lambda _:[])
        for faces in (['公園','講演'],['講演','公園']):
            index=SimpleNamespace(surfaces_for_reading=lambda _:faces)
            with patch.object(K,'available',return_value=True),patch.object(K,'tier',return_value=1), \
                 patch.object(C,'_table_cost',side_effect=lambda s:{'公園':10,'講演':12}[s]):
                self.assertEqual(C._index_face('こうえん',store,index),'公園')
                self.assertIsNone(C._index_face('こうえん',store,index,require_unique=True))

    def test_unique_conversion_face_does_not_count_duplicate_dictionary_entries(self):
        store=SimpleNamespace(lookup=lambda _:[])
        index=SimpleNamespace(surfaces_for_reading=lambda _:['確認','確認'])
        with patch.object(K,'available',return_value=True),patch.object(K,'tier',return_value=1), \
             patch.object(C,'_table_cost',return_value=10):
            self.assertEqual(C._index_face('かくにん',store,index,require_unique=True),'確認')

    def test_equal_ranked_established_faces_have_a_stable_first_choice(self):
        for faces in (['公園','講演'],['講演','公園']):
            store=SimpleNamespace(lookup=lambda _:[dict(surface=s,count=2) for s in faces])
            with patch.object(C,'_kango_tier_of',return_value=1),patch.object(C,'_table_cost',return_value=10):
                self.assertEqual(C._lu_dominant('こうえん',store),('公園',3))

    def test_an_ordinary_homophone_prevents_a_restricted_reading_claim(self):
        usage={'按針':3,'宣旨':3,'戦時':2}
        readings={'按針':'あんじん','宣旨':'せんじ','戦時':'せんじ'}
        self.tearDown()
        with patch.object(K,'_TABLE',{'戦時':2}),patch.object(K,'_USAGE',usage), \
             patch.object(M,'dictionary_inflections',side_effect=lambda word:
                 (('名詞,一般,*,*','*',word,readings[word]),) if word in readings else ()), \
             patch.object(C,'table_surfaces_for_reading',return_value=[]):
            self.assertTrue(K.reading_is_explicitly_restricted('あんじん'))
            self.assertFalse(K.reading_is_explicitly_restricted('せんじ'))
            self.assertFalse(K.reading_is_explicitly_restricted('未知の読み'))


if __name__=='__main__':unittest.main()
