# -*- coding: utf-8 -*-
"""A result writing system is distinct from a borrowed item's return owner."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('返還'),'requires native dictionary')
class WritingSystemConversionTests(unittest.TestCase):
    def tokens(self,text):
        return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
                for t in M.tokenize(text)]

    def test_both_argument_orders_use_their_actual_cases(self):
        for text in ('ひらがなを漢字に返還します。','漢字に平仮名を返還します。',
                     '漢字を仮名に返還します。','平仮名を片仮名に返還します。',
                     '漢字にひらがなを返還します。','漢字をひらがなに返還します。'):
            with self.subTest(text=text):
                self.assertTrue(S.conflicting_object_predicates(text,self.tokens(text)))
                self.assertTrue(S.changed_object_conflict_allowed(text,text.replace('返還','変換')))
                self.assertFalse(S.changed_object_conflict_allowed(text,text.replace('返還','転記')))

    def test_source_readings_and_other_senses_are_not_inferred(self):
        for text in ('資料を本人に返還します。','文字の資料を作者に返還します。',
                     '漢字を作者に返還します。','ひらがなを漢字に変換します。',
                     '文字を元に返還します。','漢字を平仮名に戻します。',
                     'ひらがなを漢字に返還すると説明しました。',
                     'ひらがなを漢字に返還する人です。',
                     'ぷねらを漢字に返還します。','漢字をぷねらに返還します。',
                     '平仮名をひらがなに返還します。','かなをカナに返還します。',
                     'かんじをひらがなに返還します。','ひらがなを作者に返還します。'):
            self.assertFalse(S.conflicting_object_predicates(text,self.tokens(text)),text)

    def test_application_repairs_same_reading_and_preserves_quotes(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ひらがなを漢字に返還します。','漢字に平仮名を返還します。',
                     '仮名をローマ字に返還します。','漢字にひらがなを返還します。',
                     '漢字をひらがなに返還します。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text.replace('返還','変換'))
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('資料を本人に返還します。','ひらがなを漢字に変換します。',
                     '「ひらがなを漢字に返還します」という誤記です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[])

    def test_modifier_phrase_is_not_invented_as_a_single_argument_head(self):
        from reading_segments import native_literal_argument_chain
        text='ふれーむのいろをかえます'
        self.assertFalse(native_literal_argument_chain(text[:text.index('かえ')]))
        # Native parsing swallows this whole kana phrase. Existing reading
        # grammar owns its head; this semantic fallback must not invent one.
        self.assertEqual(S.object_before(text,text.index('かえ'),self.tokens),'')

    def test_literal_case_chain_never_selects_a_homophones_kanji(self):
        from reading_segments import native_literal_argument_chain as chain
        for prefix,expected in (
                ('ひらがなを漢字に',(('ひらがな','を',0,5),('漢字','に',5,8))),
                ('漢字にひらがなを',(('漢字','に',0,3),('ひらがな','を',3,8))),
                ('前文。ひらがなを漢字に',(('ひらがな','を',3,8),('漢字','に',8,11)))):
            self.assertEqual(chain(prefix),expected)
        self.assertEqual(chain('かんじをひらがなに')[0][0],'かんじ')
        for prefix in ('ぷねらを漢字に','漢字をぷねらに','ひらがなを 読んで漢字に',
                       '資料を読みてひらがなに','資料を本人に'):
            self.assertEqual(chain(prefix),(),prefix)

    def test_rejected_conversion_does_not_take_an_unfitting_homophone(self):
        import app
        from decisions import DecisionStore
        from tests_analysis_async import initial
        a=initial();ledger=DecisionStore();ledger.reject('返還','変換')
        text='ひらがなを漢字に返還します。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=ledger)
        self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
