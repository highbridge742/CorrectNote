# -*- coding: utf-8 -*-
"""Exact native form/reading must precede semantic role reuse."""
import unittest
from unittest.mock import patch
import semantic_roles as S
import morphology as M
import reading_segments as R


class NativeActionRoleTests(unittest.TestCase):
    def tearDown(self):
        S.native_verb_roles.cache_clear()
        S._native_verb_reading_lexemes.cache_clear()
        S._native_lexeme_forms.cache_clear()
        S.predicate_roles.cache_clear()

    def test_kana_role_bridge_keeps_original_inflection_and_reading(self):
        forms={'つづけ':(('動詞,自立,*,*','連用形','つづける','つづけ'),),
               'つづける':(('動詞,自立,*,*','基本形','つづける','つづける'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda w:forms.get(w,())), \
             patch.object(S,'_native_verb_reading_lexemes',return_value={'つづける':('続ける',)}), \
             patch.object(S,'VERB_ROLES',{'続ける':{'process'}}):
            self.assertEqual(S.native_verb_roles('つづけ','連用形','つづけ'),frozenset(('process',)))
            self.assertEqual(S.native_verb_roles('つづけ','未然形','つづけ'),frozenset())
            self.assertEqual(S.native_verb_roles('つづけ','連用形','つつけ'),frozenset())

    def test_dative_and_content_roles_do_not_leak_into_each_other(self):
        forms={'きき':(('動詞,自立,*,*','連用形','きく','きき'),),
               'きく':(('動詞,自立,*,*','基本形','きく','きく'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda w:forms.get(w,())), \
             patch.object(S,'_native_verb_reading_lexemes',return_value={'きく':('聞く',)}), \
             patch.object(S,'VERB_ROLES',{'聞く':{'sound'}}), \
             patch.object(S,'CASE_VERB_ROLES',{'に':{'聞く':{'person'}}}):
            self.assertEqual(S.native_verb_roles('きき','連用形','きき'),frozenset(('sound',)))
            self.assertEqual(S.native_verb_roles('きき','連用形','きき',case='に'),frozenset(('person',)))
            self.assertEqual(S.native_verb_roles('きき','連用形','きき',case='へ'),frozenset())
            self.assertEqual(S.native_verb_roles('きき','未然形','きき',case='に'),frozenset())

    def test_written_homophone_cannot_borrow_other_written_verb_roles(self):
        forms={'飼い':(('動詞,自立,*,*','連用形','飼う','かい'),),
               '飼う':(('動詞,自立,*,*','基本形','飼う','かう'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda w:forms.get(w,())), \
             patch.object(S,'_native_verb_reading_lexemes',return_value={'かう':('買う',)}):
            self.assertEqual(S.native_verb_roles('飼い','連用形','かい'),frozenset())

    def test_only_native_basic_forms_enter_the_derived_lexeme_table(self):
        forms={'続ける':(('動詞,自立,*,*','基本形','続ける','つづける'),),
               '代用':(('名詞,サ変接続,*,*','*','代用','だいよう'),)}
        S._native_verb_reading_lexemes.cache_clear()
        with patch.object(S,'VERB_ROLES',{'続ける':{'process'},'代用':{'object'},'未収録':{'text'}}), \
             patch.object(S,'SUBJECT_VERB_ROLES',{}), \
             patch.object(S,'CASE_VERB_ROLES',{}), \
             patch.object(M,'dictionary_inflections',side_effect=lambda w:forms.get(w,())):
            self.assertEqual(S._native_verb_reading_lexemes(),{'つづける':('続ける',)})

    def test_one_lexeme_must_supply_both_tail_and_semantic_role(self):
        def entry(form,base,reading):return ('動詞,自立,*,*',form,base,reading)
        forms={'かい':(entry('連用タ接続','かく','かい'),entry('連用タ接続','かぐ','かい')),
               'かく':(entry('基本形','かく','かく'),),'かぐ':(entry('基本形','かぐ','かぐ'),),
               '書い':(entry('連用タ接続','書く','かい'),),'嗅い':(entry('連用タ接続','嗅ぐ','かい'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda w:forms.get(w,())), \
             patch.object(S,'_native_verb_reading_lexemes',return_value={'かく':('書く',),'かぐ':('嗅ぐ',)}), \
             patch.object(S,'VERB_ROLES',{'書く':{'text'},'嗅ぐ':{'scent'}}), \
             patch('contextual_repair._productive_predicate',return_value=True), \
             patch('contextual_repair._allows_grammatical_tail',side_effect=lambda forms,tail,rd,face:
                   (face,tail) in (('書い','てみます'),('嗅い','でみます'))):
            self.assertEqual(S.native_verb_roles('かい','連用タ接続','かい',tail='てみます'),frozenset(('text',)))
            self.assertEqual(S.native_verb_roles('かい','連用タ接続','かい',tail='でみます'),frozenset(('scent',)))

    def test_sahen_subject_fit_requires_affirmative_evidence(self):
        # This exercises the real subject-evidence guard before native tail
        # checks. A candidate's existence is not proof about its source subject.
        R.completed_sahen_reading.cache_clear()
        with patch.object(R,'_native_nominal_reading_faces',return_value=('解決',)), \
             patch.object(M,'dictionary_inflections',return_value=(
                 ('動詞,自立,*,*','連用形','する','し'),)), \
             patch.object(S,'subject_candidate_evidence',return_value=None):
            self.assertFalse(R.completed_sahen_reading('かいけつした',allow_nonpolite=True,
                                                      subject_faces=('未分類',)))
        R.completed_sahen_reading.cache_clear()


    def test_case_roles_distinguish_content_from_destination(self):
        self.assertTrue(S.case_action_support('箱','に','保管'))
        self.assertTrue(S.case_action_support('サーバー','に','保存'))
        self.assertTrue(S.case_action_support('画像','は','保存'))
        self.assertFalse(S.case_action_support('画像','に','保存'))
        self.assertFalse(S.case_action_support('箱','に','説明'))
        self.assertFalse(S.case_action_support('画像','の','保存'))

    def test_shika_needs_native_negation_in_its_own_predicate(self):
        negative=M.Token('ない','助動詞','ない','ない',3,5,True,'*','基本形')
        connective=M.Token('て','助詞','て','て',2,3,True,'接続助詞','')
        with patch.object(M,'dictionary_inflections',return_value=(('助動詞,*,*,*','基本形','ない','ない'),)):
            with patch.object(M,'tokenize',return_value=[negative]):
                self.assertTrue(R.native_negative_predicate('しない'))
            with patch.object(M,'tokenize',return_value=[connective,negative]):
                self.assertFalse(R.native_negative_predicate('してしない'))
            with patch.object(M,'tokenize',return_value=[]):
                self.assertFalse(R.native_negative_predicate('した'))


    def test_nominal_phrase_keeps_actual_genitive_boundary_and_head(self):
        no=M.Token('の','助詞','の','の',2,3,True,'連体化','')
        R.native_nominal_phrase_faces.cache_clear()
        with patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:
                    {'ひと':('人',),'ぺーじ':('頁',)}.get(rd,())), \
             patch.object(M,'tokenize',return_value=[no]):
            self.assertEqual(R.native_nominal_phrase_faces('ひとのぺーじ'),('頁',))
        R.native_nominal_phrase_faces.cache_clear()
        with patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:
                    {'ひと':('人',),'ぺーじ':('頁',)}.get(rd,())), \
             patch.object(M,'tokenize',return_value=[]), \
             patch.object(R,'native_bare_action_faces',return_value=()):
            self.assertEqual(R.native_nominal_phrase_faces('ひとのぺーじ'),())
        R.native_nominal_phrase_faces.cache_clear()

    def test_relational_head_does_not_accept_arbitrary_noun_pairs(self):
        R.native_nominal_phrase_faces.cache_clear()
        with patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:
                    {'けっか':('結果',),'がぞう':('画像',)}.get(rd,())), \
             patch.object(M,'tokenize',return_value=[]), \
             patch.object(R,'native_bare_action_faces',side_effect=lambda rd:
                    ('検索',) if rd=='けんさく' else ()):
            self.assertEqual(R.native_nominal_phrase_faces('けんさくけっか'),('結果',))
            self.assertEqual(R.native_nominal_phrase_faces('けんさくがぞう'),())
        R.native_nominal_phrase_faces.cache_clear()


if __name__=='__main__':unittest.main()
