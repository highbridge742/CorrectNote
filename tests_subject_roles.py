"""Explicit nominative evidence ranks anomalous candidates without new detection."""
import unittest
from unittest.mock import patch
import semantic_roles as S
import morphology as M


def subject_tokens(noun='問題',particle='が',pos='名詞:一般',known=True):
    n=len(noun)
    return [(noun,pos,noun,0,n,known,''),(particle,'助詞:格助詞',particle,n,n+1,True,'')]


class SubjectRoleTests(unittest.TestCase):
    def tearDown(self):
        S._subject_predicate_roles.cache_clear()

    def test_only_an_explicit_known_nominative_supplies_subject_evidence(self):
        self.assertEqual(S.subject_before('問題が誤語',3,lambda _:subject_tokens()),'問題')
        for particle in ('を','は','に','の'):
            self.assertEqual(S.subject_before('問題'+particle+'誤語',3,lambda _:subject_tokens(particle=particle)),'')
        for pos,known in (('名詞:固有名詞',True),('名詞:一般',False),('名詞:接尾',True)):
            self.assertEqual(S.subject_before('問題が誤語',3,lambda _:subject_tokens(pos=pos,known=known)),'')

    def test_compound_subject_is_not_reduced_to_its_last_word(self):
        tokens=[('社会','名詞:一般','しゃかい',0,2,True,''),
            ('問題','名詞:一般','もんだい',2,4,True,''),('が','助詞:格助詞','が',4,5,True,'')]
        self.assertEqual(S.subject_before('社会問題が誤語',5,lambda _:tokens),'')

    def test_subject_roles_are_distinct_from_accusative_roles(self):
        with patch.object(S,'_subject_predicate_roles',return_value=('解決',frozenset({'issue'}))):
            evidence=S.subject_candidate_evidence('問題','候補','')
            self.assertEqual(evidence['shared_roles'],['issue'])
            self.assertFalse(S.subject_candidate_evidence('担当者','候補','')['shared_roles'])
        with patch.object(S,'_subject_predicate_roles',return_value=('解説',frozenset({'person'}))):
            self.assertTrue(S.subject_candidate_evidence('担当者','候補','')['shared_roles'])
            self.assertFalse(S.subject_candidate_evidence('問題','候補','')['shared_roles'])

    def test_unknown_semantics_are_not_a_negative_judgement(self):
        self.assertIsNone(S.subject_candidate_evidence('架空名','解決した',''))
        with patch.object(S,'_subject_predicate_roles',return_value=('説明',frozenset({'person'}))):
            result=S.subject_candidate_evidence('本','候補','')
        self.assertEqual(result['shared_roles'],[])
        self.assertNotIn('invalid',result)

    def test_voice_changing_suffix_does_not_use_active_subject_roles(self):
        tokens=[M.Token('解決','名詞','解決','かいけつ',0,2,True,'サ変接続'),
                M.Token('さ','動詞','する','さ',2,3,True,'自立'),
                M.Token('れる','動詞','れる','れる',3,5,True,'接尾')]
        with patch.object(S,'_action_head',return_value='解決'),patch.object(M,'tokenize',return_value=tokens):
            self.assertEqual(S._subject_predicate_roles('解決される',''),('',frozenset()))

    def test_native_conjugation_keeps_the_same_subject_role(self):
        t=M.Token('届い','動詞','届く','とどい',0,2,True,'自立',infl_form='連用タ接続')
        with patch.object(S,'_action_head',return_value='届いた'),patch.object(M,'tokenize',return_value=[t]), \
             patch.object(M,'dictionary_inflections',return_value=(('動詞,自立,*,*','連用タ接続','届く','とどい'),)):
            self.assertEqual(S._subject_predicate_roles('届いた','')[1],frozenset({'text','information'}))

    def test_positive_role_lookup_does_not_call_anomaly_detection(self):
        with patch.object(S,'_subject_predicate_roles',return_value=('解決',frozenset({'issue'}))), \
             patch('oddness.is_odd_run') as detect:
            S.subject_candidate_evidence('問題','候補','')
        detect.assert_not_called()


if __name__=='__main__':unittest.main()
