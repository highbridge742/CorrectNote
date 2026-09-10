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

    def test_roles_supply_positive_evidence_without_declaring_other_senses_invalid(self):
        self.assertTrue(S.support('理由','説明'))
        self.assertTrue(S.support('結果','記録'))
        self.assertTrue(S.support('本','再版'))
        self.assertTrue(S.support('資金','寄付'))
        self.assertFalse(S.support('理由','再版'))
        self.assertFalse(S.support('未知','説明'))
        self.assertFalse(S.support('理由','未知'))

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
        with patch.object(M,'tokenize',side_effect=lambda s:[noun] if s=='説明' else [suru] if s=='します' else [no]):
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


if __name__=='__main__':unittest.main()
