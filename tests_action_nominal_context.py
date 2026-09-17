# -*- coding: utf-8 -*-
"""Native action nouns, exact kana compounds and closed object meaning."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('する'), 'requires native dictionary')
class ActionNominalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial();cls.a.context_vec=None

    def correct(self,text,decisions=None):
        import app
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            context_vec=None,decisions=decisions or self.a.decisions,input_method='kana')

    def legacy(self,text):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]

    def test_native_action_noun_keeps_argument_roles_and_process_use(self):
        for word in ('入力','作成','検索','文字入力','資料作成','平仮名入力'):
            with self.subTest(word=word):self.assertIn('process',S.nominal_roles(word))
        self.assertTrue(S.support('情報','検索'))
        self.assertTrue(S.support('資料','作成'))
        self.assertFalse(S.support('情報','食事'))
        for word in ('情報食事','未知入力','猫入力','入力者','入力太郎'):
            with self.subTest(word=word):self.assertNotIn('process',S.nominal_roles(word))

    def test_reading_compounds_need_both_native_nouns_and_semantic_connection(self):
        for text in ('じょうほうけんさく','しりょうさくせい','ひらがなにゅうりょく'):
            with self.subTest(text=text):self.assertTrue(R.native_relational_compound_heads(text))
        for text in ('じょうほうしょくじ','ひらがなりょく','ひらがにゅうりょく',
                     'ねこにゅうりょく','みちなにゅうりょく'):
            with self.subTest(text=text):self.assertFalse(R.native_relational_compound_heads(text))
        for text in ('きょじんかくにん','じょうほうけんさくをためします。','ひらがなにゅうりょくをためします。',
                     'しりょうさくせいをためします。','もじにゅうりょくをためします。'):
            with self.subTest(text=text):
                r=self.correct(text)
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])

    def test_closed_source_frames_preserve_compounds_voice_and_clause_scope(self):
        for text in ('交通費を生産します。','宿泊費を製造しました。','出張費を量産します。'):
            with self.subTest(text=text):self.assertTrue(S.conflicting_object_predicates(text,self.legacy(text)))
        for text in ('部品を生産します。','金を生産します。','経費を生産する仕組みと比較します。',
                     '交通費を生産費に加えます。','経費を生産させます。','経費を生産して調整します。',
                     '未知交通費を生産します。'):
            with self.subTest(text=text):self.assertFalse(S.conflicting_object_predicates(text,self.legacy(text)))
        for text in ('意見を繁栄します。','要望を繁盛します。'):
            with self.subTest(text=text):self.assertTrue(S.subject_only_predicate_spans(text,self.legacy(text)))
        for text in ('町が繁栄します。','地域を繁栄させます。','地域を繁栄する町にします。'):
            with self.subTest(text=text):self.assertFalse(S.subject_only_predicate_spans(text,self.legacy(text)))

    def test_actual_adjacent_repairs_retain_original_nominal_and_normal_alternatives(self):
        for text in ('もじにゅうりょくをためはます。','もじにゅうりょくをためさします。',
                     'もじにゅうりょくをためしまきす。'):
            with self.subTest(text=text):
                r=self.correct(text)
                self.assertEqual(r['corrected'],'もじにゅうりょくをためします。')
                self.assertEqual(r['odd_spans'],[])
        for text in ('もんじにゅうりょく','もじにゅうりょくく',
                     '町が繁栄します。','意見を反映します。','部品を生産します。',
                     '交通費を精算します。','旅費を清算します。'):
            with self.subTest(text=text):self.assertEqual(self.correct(text)['corrected'],text)
        self.assertEqual(self.correct('意見を繁栄します。')['corrected'],'意見を反映します。')
        # Both native settlement senses fit expenses; no exact 精算 claim.
        self.assertIn(self.correct('交通費を生産します。')['corrected'],
                      ('交通費を精算します。','交通費を清算します。'))

    def test_common_stop_final_validation_and_purple_ledger_remain_distinct(self):
        from decisions import DecisionStore
        import corrector as C
        source='意見を繁栄します。'
        decisions=DecisionStore();decisions.protect('繁栄')
        self.assertEqual(self.correct(source,decisions)['corrected'],source)
        decisions=DecisionStore();decisions.leave_odd_alone('繁栄')
        self.assertEqual(self.correct(source,decisions)['corrected'],'意見を反映します。')
        with patch.object(C,'_check_replacement',return_value=(None,'test_rejected')):
            r=self.correct(source)
        self.assertEqual(r['corrected'],source)
        self.assertTrue(r['odd_spans'])


if __name__=='__main__':unittest.main()
