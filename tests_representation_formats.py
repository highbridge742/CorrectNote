# -*- coding: utf-8 -*-
"""Representation properties differ from the document and its ownership."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('変換'),'requires native dictionary')
class RepresentationFormatTests(unittest.TestCase):
    def tokens(self,text):
        return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
                for t in M.tokenize(text)]

    def test_same_property_roles_supply_the_conflict_and_positive_fit(self):
        for noun in ('保存形式','ファイル形式','画像形式','文字コード'):
            text=noun+'を返還します。'
            self.assertTrue(S.conflicting_object_predicates(text,self.tokens(text)),text)
            self.assertTrue(S.changed_object_conflict_allowed(text,text.replace('返還','変換')),text)
            self.assertFalse(S.changed_object_conflict_allowed(text,text.replace('返還','返却')),text)
            self.assertIn('表現形式',S.object_predicate_conflict_reason(noun,'返還'))
        # Native IPADIC splits エンコーディング at the proper noun エン.
        # Its category alone does not attest the whole nominal boundary.
        self.assertIn('representation_format',S.nominal_roles('エンコーディング'))
        self.assertFalse(S.case_action_support('保存形式','に','返還'))

    def test_classified_compounds_keep_the_same_head_in_both_case_orders(self):
        for text in ('文字コードをファイル形式に変換します。',
                     'ファイル形式に文字コードを変換します。'):
            start=text.index('変換')
            self.assertEqual(S.object_before(text,start,self.tokens),'文字コード')
            self.assertEqual(S.case_argument_before(text,start,self.tokens,True),('ファイル形式','に'))
        text='保存形式の資料を返還します。'
        self.assertEqual(S.object_before(text,text.index('返還'),self.tokens),'資料')

    def test_actual_nominal_head_and_closed_action_remain_required(self):
        for text in ('ファイルを返還します。','資料を返還します。','形式を返還します。',
                     '書式を返還します。','保存形式の資料を返還します。',
                     '文字コードの権利を返還します。','文字コードを変換します。',
                     '保存形式を返還する方法です。','ぷねらを返還します。'):
            self.assertFalse(S.conflicting_object_predicates(text,self.tokens(text)),text)

    def test_application_keeps_literal_meaning_and_quotes(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('保存形式を返還します。','画像形式を返還しました。',
                     '文字コードを返還します。','ファイル形式を返還して内容を確認します。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text.replace('返還','変換'))
            self.assertEqual(result.get('odd_spans'),[],text)
        for text in ('保存形式を変換します。','ファイルを返還します。',
                     'ほぞんけいしきをへんかんします。',
                     '「保存形式を返還します」という誤記です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)

    def test_rejection_does_not_authorize_another_unfitting_word(self):
        import app
        from decisions import DecisionStore
        from tests_analysis_async import initial
        a=initial();ledger=DecisionStore();ledger.reject('返還','変換')
        text='保存形式を返還します。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=ledger)
        self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
