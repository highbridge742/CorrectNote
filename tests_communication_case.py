# -*- coding: utf-8 -*-
"""A communication channel, content and predicate retain separate roles."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('メール'),'requires native dictionary')
class CommunicationCaseTests(unittest.TestCase):
    def test_channel_has_its_own_case_role(self):
        for noun in ('メール','電話','手紙','電報'):
            self.assertTrue(S.case_action_support(noun,'で','伝える'),noun)
        for noun in ('椅子','鉛筆','布'):
            self.assertFalse(S.case_action_support(noun,'で','伝える'),noun)
        self.assertFalse(S.case_action_support('メール','で','食べる'))
        self.assertFalse(S.case_action_support('メール','に','送る'))

    def test_copular_parse_is_only_an_alternative_with_positive_action_fit(self):
        for text in ('めーるでおくります','でんわでつたえます',
                     'しりょうをめーるでおくります','かいぎのしりょうをめーるでおくります',
                     'めーるでしりょうをおくります'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('めーるでたべます','めーるでしりょうをたべます',
                     'めーるでぷねらをおくります','めーるでおくり','めーるでほんです'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_source_copulas_and_natural_channels_are_held(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('めーるでおくります。','しりょうをめーるでおくります。',
                     'めーるでしりょうをおくります。','これはメールでした。',
                     '静かで美しい場所です。','学生で働いています。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)

    def test_typo_repair_keeps_the_original_channel_and_object(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        text='かいぎのしりょうをめーるでおきります。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'かいぎのしりょうをめーるでおくります。')
        self.assertEqual(result.get('odd_spans'),[])
        # The hand-written おすり example is not a physical neighbour
        # of おくり; it remains a prohibition control, not a repair goal.
        text='かいぎのしりょうをめーるでおすります。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
