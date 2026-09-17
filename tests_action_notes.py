# -*- coding: utf-8 -*-
"""Shared usage knowledge and grammatical/semantic evidence for action notes."""
import unittest
from unittest.mock import patch
import kango_tier as K
import morphology as M
import reading_segments as R
import semantic_roles as S


class ActionNoteTests(unittest.TestCase):
    def tearDown(self):
        for f in (K._explicit_reading_faces,R._native_nominal_reading_faces,
                  R.native_bare_action_faces,R.native_nominal_phrase_faces,R._native_action_note_heads,
                  R.completed_native_action_note,R.completed_native_reading,
                  R.completed_sahen_reading,R.completed_native_reading_clause):
            f.cache_clear()

    def test_older_positive_usage_has_native_reading_evidence_too(self):
        def native(word):
            entries={'既存':(('名詞,サ変接続,*,*','*','既存','きそん'),),
                     '追加':(('名詞,サ変接続,*,*','*','追加','ついか'),)}
            return entries.get(word,())
        K._explicit_reading_faces.cache_clear()
        with patch.object(K,'_load',return_value={}), \
             patch.object(K,'_TABLE',{'既存':1,'未分類':3}), \
             patch.object(K,'_USAGE',{'追加':2,'辞書不在':1}), \
             patch.object(K,'_READING_USAGE',{}), \
             patch.object(M,'dictionary_inflections',side_effect=native):
            self.assertEqual(K._explicit_reading_faces(),{'きそん':{'既存'},'ついか':{'追加'}})

    def test_bare_action_requires_native_nominal_reading_and_sahen(self):
        forms={'保存':(('名詞,サ変接続,*,*','*','保存','ほぞん'),),
               '普通':(('名詞,一般,*,*','*','普通','ふつう'),)}
        with patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:tuple(forms)), \
             patch.object(M,'dictionary_inflections',side_effect=lambda w:forms[w]):
            self.assertEqual(R.native_bare_action_faces('ほぞん'),('保存',))
            self.assertEqual(R.native_bare_action_faces('ふつう'),())
            self.assertEqual(R.native_bare_action_faces('べつよみ'),())

    def test_note_reuses_proven_action_and_passes_following_meaning(self):
        calls=[]
        def clause(text,**kwargs):
            calls.append((text,kwargs))
            return '確認' if text=='ないようをかくにんして' else False
        with patch.object(R,'native_bare_action_faces',side_effect=lambda s:('保存',) if s=='ほぞん' else ()), \
             patch.object(R,'completed_native_reading_clause',side_effect=clause):
            self.assertTrue(R.completed_native_action_note('ないようをかくにんしてほぞん'))
        text,kwargs=next(r for r in calls if r[0]=='ないようをかくにんして')
        self.assertTrue(kwargs['require_object_fit'])
        self.assertTrue(kwargs['return_action'])
        self.assertEqual(kwargs['action_note_following'],('保存',))

    def test_incomplete_or_adnominal_tail_is_not_an_action_note(self):
        with patch.object(R,'native_bare_action_faces',return_value=('保存',)), \
             patch.object(R,'completed_native_reading_clause',return_value='確認'):
            for text in ('かくにんしたほぞん','かくにんするほぞん',
                         'かくにんしほぞん','かくにんてほぞん'):
                self.assertFalse(R.completed_native_action_note(text),text)

    def test_unproven_left_clause_does_not_gain_evidence_from_right_action(self):
        with patch.object(R,'native_bare_action_faces',return_value=('保存',)), \
             patch.object(R,'completed_native_reading_clause',return_value=False):
            self.assertFalse(R.completed_native_action_note('かくにんしてほぞん'))

    def test_shared_action_roles_require_positive_linkage(self):
        for a,b in (('確認','保存'),('優先','補正'),('入力','終了'),
                    ('起動','確認'),('掃除','洗濯'),('集計','保存')):
            self.assertTrue(S.action_note_support(a,b),(a,b))
        with patch.object(S,'predicate_roles',side_effect=lambda s:
                frozenset(('information',)) if s=='保存' else frozenset()):
            self.assertFalse(S.action_note_support('堪忍','保存'))
            self.assertFalse(S.action_note_support('収賄','保存'))
            self.assertFalse(S.action_note_support('未分類','終了'))

    def test_activity_link_does_not_invent_an_accusative_frame(self):
        self.assertTrue(S.action_note_support('訓練','上達'))
        self.assertTrue(S.action_note_support('運動','補給'))
        self.assertTrue(S.action_note_support('補給','休息'))
        self.assertFalse(S.action_note_support('収賄','保存'))
        with patch.object(S,'_action_head',return_value='上達'):
            e=S.candidate_evidence('人','上達','します')
            self.assertFalse(e['shared_roles'])

    def test_introductory_word_needs_its_native_role_and_unchanged_action(self):
        word=M.Token('そして','接続詞','そして','そして',0,3,True,'*','')
        R.native_action_note_introduction.cache_clear()
        with patch.object(M,'tokenize',return_value=[word]), \
             patch.object(R,'native_bare_action_faces',side_effect=lambda rd:('保存',) if rd=='ほぞん' else ()):
            self.assertTrue(R.native_action_note_introduction('そしてほぞん'))
            self.assertFalse(R.native_action_note_introduction('そしてほぞんしたます'))
        R.native_action_note_introduction.cache_clear()
        wrong=M.Token('そして','名詞','そして','そして',0,3,True,'一般','')
        with patch.object(M,'tokenize',return_value=[wrong]), \
             patch.object(R,'native_bare_action_faces',return_value=('保存',)):
            self.assertFalse(R.native_action_note_introduction('そしてほぞん'))
        R.native_action_note_introduction.cache_clear()


if __name__=='__main__':unittest.main()
