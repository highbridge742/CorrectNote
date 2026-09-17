# -*- coding: utf-8 -*-
"""The next clause can close the previous case frame without guessing intent."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('繁栄'),'requires native dictionary')
class IndependentObjectClauseTests(unittest.TestCase):
    def tokens(self,text):
        return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
                for t in M.tokenize(text)]

    def test_next_object_requires_native_grammar_not_role_coverage(self):
        for text in ('仕様を直します。','予定を決めます。','文章を読みます。',
                     '古い仕様を直します。','次の計画を決めます。','会議の資料を保存します。'):
            with self.subTest(text=text):self.assertTrue(S._independent_accusative_clause(text))
        for text in ('仕様を直し','仕様をしらゆほします。','仕様に戻ります。',
                     '死んだ人を見ます。','仕様を直す人です。','資料を読んで寝ます。',
                     '仕様を直すと言います。','「仕様を直します」',
                     '仕様を直しますです。','仕様を直させます。','仕様を直されます。'):
            with self.subTest(text=text):self.assertFalse(S._independent_accusative_clause(text))

    def test_only_the_anomalous_predicate_stem_receives_the_span(self):
        for text,noun,predicate in (
                ('意見を繁栄して仕様を直します。','意見','繁栄'),
                ('理由を絶命して資料を保存します。','理由','絶命'),
                ('要望を繁栄して、古い仕様を直します。','要望','繁栄')):
            with self.subTest(text=text):
                start=text.index(predicate)
                self.assertEqual(S.subject_only_predicate_spans(text,self.tokens(text)),
                    [(noun,predicate,start,start+len(predicate))])
        text='日程を長生して予定を決めます。'
        self.assertEqual(S.conflicting_object_predicates(text,self.tokens(text)),[('日程','長生',3,5)])

    def test_shared_or_open_object_attachment_stays_open(self):
        for text in ('子供を死んだ人の家に連れていきます。',
                     '子供を泣きながら抱きます。','子供を死ぬまで見守ります。',
                     '意見を繁栄して','意見を繁栄して、','意見を繁栄して仕様を直し',
                     '意見を繁栄して書いた人に見せます。',
                     '地域を繁栄させて生活を変えます。',
                     '地域が繁栄して生活を変えます。',
                     '意見を繁栄すると仕様を変えます。'):
            with self.subTest(text=text):
                self.assertEqual(S.subject_only_predicate_spans(text,self.tokens(text)),[])

    def test_application_corrects_connected_homophones_and_keeps_normals(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
                ('意見を繁栄して仕様を直します。','意見を反映して仕様を直します。'),
                ('日程を長生して予定を決めます。','日程を調整して予定を決めます。'),
                ('意見を反映して仕様を直します。','意見を反映して仕様を直します。'),
                ('地域を繁栄させて生活を変えます。','地域を繁栄させて生活を変えます。'),
                ('「意見を繁栄して仕様を直します」という誤記です。','「意見を繁栄して仕様を直します」という誤記です。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
