# -*- coding: utf-8 -*-
"""General argument roles rank candidates only after a grammatical repair exists."""
import unittest
from unittest.mock import patch
import morphology as M
import semantic_roles as S


class SemanticRoleTests(unittest.TestCase):
    def tearDown(self):
        S._action_head.cache_clear()
        S.predicate_roles.cache_clear()
        S.native_verb_roles.cache_clear()

    def test_roles_supply_positive_evidence_without_declaring_other_senses_invalid(self):
        self.assertTrue(S.support('理由','説明'))
        self.assertTrue(S.support('結果','記録'))
        self.assertTrue(S.support('本','再版'))
        self.assertTrue(S.support('資金','寄付'))
        self.assertFalse(S.support('理由','再版'))
        self.assertFalse(S.support('未知','説明'))
        self.assertFalse(S.support('理由','未知'))

    @unittest.skipUnless(M.dictionary_inflections('食器'),'requires native dictionary')
    def test_original_kana_accusative_shares_native_noun_evidence(self):
        for noun in ('食器','しょっき'):
            proof=S.candidate_evidence(noun,'あらってたなにもどします','',before=noun+'を')
            self.assertTrue(proof and proof['shared_roles'],noun)
            self.assertIsNone(S.candidate_evidence(noun,'ふらっとたなにもどします','',before=noun+'を'))
        for noun in ('布施','ふせ','しらゆほ'):
            proof=S.candidate_evidence(noun,'あらいます','',before=noun+'を')
            self.assertFalse(proof and proof['shared_roles'],noun)
        self.assertFalse(S.candidate_evidence('水','食べます','')['shared_roles'])

    @unittest.skipUnless(M.dictionary_inflections('食器'),'requires native dictionary')
    def test_kana_object_evidence_reaches_candidate_rank(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
            ('しょっきをふらってたなにもどします。','しょっきをあらってたなにもどします。'),
            ('しょっきをあらってたなにもどします。','しょっきをあらってたなにもどします。'),
            ('しょっきをあらってはたなにもどします。','しょっきをあらってはたなにもどします。'),
            ('ふらっとたなにもどります。','ふらっとたなにもどります。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],expected,text)
            self.assertEqual(result.get('odd_spans'),[],text)

    @unittest.skipUnless(M.dictionary_inflections('保存'),'requires native dictionary')
    def test_kana_and_written_suru_actions_share_the_same_object_proof(self):
        for noun in ('データ','でーた'):
            written=S.candidate_evidence(noun,'保存','します',before=noun+'を')
            kana=S.candidate_evidence(noun,'ほぞん','します',before=noun+'を')
            self.assertTrue(written and written['shared_roles'])
            self.assertTrue(kana and kana['shared_roles'])
            self.assertEqual(kana['shared_roles'],written['shared_roles'])
        for action in ('せいり','整理'):
            self.assertTrue(S.candidate_evidence('しりょう',action,'してください')['shared_roles'])
        for noun,action,tail in (('野菜','ほぞん','しますです'),('野菜','せいり','のため'),
                                 ('資料','にく','します'),('資料','せいり','し')):
            proof=S.candidate_evidence(noun,action,tail)
            self.assertFalse(proof and proof['shared_roles'],(noun,action,tail))

    def test_food_drink_and_medicine_do_not_share_every_action(self):
        self.assertTrue(S.support('野菜','調理'))
        self.assertTrue(S.support('薬','服用'))
        for obj,verb in (('野菜','飲む'),('水','食べる'),('薬','食べる'),('人','キス')):
            with self.subTest(obj=obj,verb=verb):
                self.assertFalse(S.support(obj,verb))

    def test_explicit_accusative_head_keeps_original_boundary(self):
        ts=[('理由','名詞:一般','りゆう',0,2,True,''),
            ('を','助詞:格助詞:一般','を',2,3,True,'')]
        self.assertEqual(S.object_before('理由を説明',3,lambda s:ts),'理由')
        self.assertEqual(S.object_before('理由を 説明',4,lambda s:ts),'')
        self.assertEqual(S.object_before('理由を説明',2,lambda s:ts),'')
        self.assertEqual(S.object_before('理由に説明',3,lambda s:[ts[0],('に',)+ts[1][1:]]),'')

    def test_names_unknowns_suffixes_and_gaps_do_not_become_argument_evidence(self):
        p=('を','助詞:格助詞:一般','を',2,3,True,'')
        for n in (('理由','名詞:固有名詞:人名','りゆう',0,2,True,''),
                  ('理由','名詞:一般','りゆう',0,2,False,''),
                  ('理由','名詞:接尾:一般','りゆう',0,2,True,''),
                  ('理由','名詞:一般','りゆう',0,1,True,'')):
            self.assertEqual(S.object_before('理由を説明',3,lambda s:[n,p]),'')

    def test_nominal_role_requires_the_actual_suru_connection(self):
        noun=M.Token('説明','名詞','説明','せつめい',0,2,True,'サ変接続')
        suru=M.Token('し','動詞','する','し',0,1,True,'自立','連用形')
        no=M.Token('の','助詞','の','の',0,1,True,'連体化')
        def native(text):
            if text=='説明':return [noun]
            if text=='説明します':return [noun,M.Token('し','動詞','する','し',2,3,True,'自立','連用形')]
            if text=='説明のため':return [noun,M.Token('の','助詞','の','の',2,3,True,'連体化')]
            return [suru] if text=='します' else [no]
        with patch.object(M,'tokenize',side_effect=native), \
             patch.object(M,'native_suru_form',side_effect=lambda sf,form,rd,*args:(sf,form,rd)==('し','連用形','し')):
            self.assertTrue(S.candidate_support('理由','説明','します'))
            self.assertFalse(S.candidate_support('理由','説明','のため'))
        self.assertFalse(S.candidate_support('未知','説明','します'))

    def test_inflected_predicate_uses_its_native_base_and_reading(self):
        verb=M.Token('並べ','動詞','並べる','ならべ',0,2,True,'自立','連用形')
        entries=(('動詞,自立,*,*','連用形','並べる','ならべ'),
                 ('動詞,自立,*,*','命令ｅ','別の原形','べつ'))
        with patch.object(M,'tokenize',return_value=[verb]),patch.object(M,'dictionary_inflections',return_value=entries):
            self.assertTrue(S.candidate_support('書類','並べました',''))
            self.assertFalse(S.candidate_support('理由','並べました',''))

    def test_homographic_noun_uses_the_verb_role_in_its_actual_te_context(self):
        noun=M.Token('片付け','名詞','片付け','かたづけ',0,3,True,'一般')
        verb=M.Token('片付け','動詞','片付ける','かたづけ',0,3,True,'自立','連用形')
        te=M.Token('て','助詞','て','て',3,4,True,'接続助詞')
        forms=(('動詞,自立,*,*','連用形','片付ける','かたづけ'),)
        S.native_verb_roles.cache_clear()
        with patch.object(M,'tokenize',side_effect=lambda text:[verb,te] if text=='片付けて' else [noun]), \
             patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertTrue(S.candidate_support('道具','片付け','て'))
            self.assertFalse(S.predicate_roles('片付け'))

    def test_actual_left_context_keeps_homographic_verb_reading(self):
        verb=M.Token('並べ','動詞','並べる','ならべ',3,5,True,'自立','連用形')
        adverb=M.Token('並べて','副詞','並べて','なべて',0,3,True,'一般')
        entries=(('動詞,自立,*,*','連用形','並べる','ならべ'),)
        with patch.object(M,'tokenize',side_effect=lambda text:[verb] if text.startswith('荷物を') else [adverb]), \
             patch.object(M,'dictionary_inflections',return_value=entries):
            self.assertIsNone(S.candidate_evidence('荷物','並べ','てから'))
            e=S.candidate_evidence('荷物','並べ','てから',before='荷物を')
            self.assertEqual(e['shared_roles'],['object'])

    def test_candidate_compound_needs_an_operation_or_lexical_relation(self):
        with patch('seed_japanese.is_unit',return_value=False):
            for left,right in (('自動','入力'),('簡易','入力'),('右','スクロール'),('かな','入力'),('カタカナ','入力'),('本人','確認'),('巨人','確認')):
                self.assertTrue(S.nominal_compound_support(left,right),(left,right))
            for left,right in (('意味','ストール'),('文書','乳力'),('右','インストール'),('本人','飲む'),('巨人','服用')):
                self.assertFalse(S.nominal_compound_support(left,right),(left,right))

    def test_unknown_argument_needs_no_predicate_analysis(self):
        with patch.object(S,'_action_head') as analyze:
            self.assertIsNone(S.candidate_evidence('未知','説明','します'))
        analyze.assert_not_called()

    def test_diagnostics_identify_roles_and_knowledge_version(self):
        with patch.object(S,'_action_head',return_value='説明'):
            e=S.candidate_evidence('理由','説明','します')
        self.assertEqual(e['object'],'理由')
        self.assertEqual(e['predicate'],'説明')
        self.assertEqual(e['shared_roles'],['information'])
        self.assertEqual(e['version'],S.KNOWLEDGE_VERSION)


    def test_dative_argument_does_not_hide_the_explicit_object(self):
        ts=[('本','名詞:一般','ほん',0,1,True,''),('を','助詞:格助詞','を',1,2,True,''),
            ('友人','名詞:一般','ゆうじん',2,4,True,''),('に','助詞:格助詞','に',4,5,True,'')]
        self.assertEqual(S.object_before('本を友人に貸す',5,lambda s:ts),'本')
        self.assertEqual(S.object_before('本を友人に 貸す',6,lambda s:ts),'')
        self.assertTrue(S.support('本','貸す'))
        self.assertFalse(S.support('理由','貸す'))
        other=ts[:2]+[('読み','動詞:自立','よみ',2,4,True,'連用形'),
            ('て','助詞:接続助詞','て',4,5,True,''),('友人','名詞:一般','ゆうじん',5,7,True,''),
            ('に','助詞:格助詞','に',7,8,True,'')]
        self.assertEqual(S.object_before('本を読みて友人に話す',8,lambda s:other),'')


    def test_native_adverbial_keeps_argument_but_does_not_cross_a_predicate(self):
        noun=('文字','名詞:一般','もじ',0,2,True,'')
        case=('を','助詞:格助詞:一般','を',2,3,True,'')
        manner=('大きく','形容詞:自立','おおきく',3,6,True,'連用テ接続')
        forms=(('形容詞,自立,*,*','連用テ接続','大きい','おおきく'),)
        with patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertEqual(S.object_before('文字を大きく描く',6,lambda _:[noun,case,manner]),'文字')
            self.assertEqual(S.object_before('文字を大きく 描く',7,lambda _:[noun,case,manner]),'')
            other=('読ん','動詞:自立','よん',3,5,True,'連用タ接続')
            te=('で','助詞:接続助詞','で',5,6,True,'')
            self.assertEqual(S.object_before('文字を読んで描く',6,lambda _:[noun,case,other,te]),'')
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertEqual(S.object_before('文字を大きく描く',6,lambda _:[noun,case,manner]),'')



    def test_physical_tools_keep_their_own_meaning(self):
        for text in ('筆','筆ペン','ボールペン','消しゴム','定規','刷毛','はけ','ハケ',
                     '箒','ほうき','ホウキ','ブラシ','雑巾','ぞうきん','ゾウキン'):
            with self.subTest(text=text):self.assertIn('object',S.nominal_roles(text))
        for text in ('放棄','蜂起','布施','不出','しらゆほ'):
            with self.subTest(text=text):self.assertNotIn('object',S.nominal_roles(text))

    @unittest.skipUnless(M.dictionary_inflections('筆'),'requires native dictionary')
    def test_native_tool_objects_share_normal_and_repaired_clause_proof(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('かいてはけをあらいます。','かいてはけをあらいます。'),
            ('ほうきをあらいます。','ほうきをあらいます。'),
            ('ふでをあらいます。','ふでをあらいます。'),
            ('ぶらしをつかいます。','ぶらしをつかいます。'),
            ('ぞうきんをほします。','ぞうきんをほします。'),
            ('ふでをあらいんす。','ふでをあらいます。'),
            ('権利を放棄します。','権利を放棄します。'),
            ('軍が蜂起します。','軍が蜂起します。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])

if __name__=='__main__':unittest.main()
