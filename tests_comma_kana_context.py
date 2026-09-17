# -*- coding: utf-8 -*-
"""Keep full-source judgments when independent kana frames surround commas."""
import unittest
import morphology as M
import contextual_repair as CR
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('借りる'),'requires native dictionary')
class CommaKanaContextTests(unittest.TestCase):
    @staticmethod
    def reading(text):
        return ''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                       else t.reading if t.has_reading else t.surface for t in M.tokenize(text))

    def test_original_purple_grammar_is_shared_without_a_new_anomaly(self):
        import corrector as C
        import oddness as O
        import pos_grammar as P
        from tests_analysis_async import initial
        a=initial();tok=C.make_tokenizer(a.store)
        text='としょかんでかりたほきんをかえして、やさいをこまかくきすります'
        native=O.is_odd_run(text,tok,with_spans=True,store=a.store,
                            dict_index=a.dict_index,complete_line=True)
        grammar=P.odd_kana_spans(text,a.dict_index,a.store)
        self.assertTrue(grammar)
        targets=CR._comma_native_kana_targets(text,0,len(text),tok,a.store,a.dict_index,native,grammar)
        self.assertEqual({t.text for t in targets},{'ほきん','こまかくきすります'})
        for target in targets:
            self.assertEqual(target.source,text)
            self.assertTrue(target.anomalies)
            self.assertNotIn('、',target.context)
        self.assertFalse(CR._comma_native_kana_targets(text,0,len(text),tok,a.store,a.dict_index,(),()))
        # A separated object and verb still have their original broad context.
        self.assertIsNone(CR._SEPARATOR.search('、'))

    def test_wide_final_validation_cannot_borrow_another_clause(self):
        text='としょかんでかりたほきんをかえして、やさいをこまかくきります'
        start=text.index('ほきん')
        self.assertTrue(R.native_modified_argument_slots(text))
        self.assertTrue(CR._changed_genitive_object_allowed(text,start,start+3,'ほん'))
        self.assertFalse(CR._changed_genitive_object_allowed(text,start,start+3,'平和'))
        self.assertFalse(CR._changed_genitive_object_allowed(text,0,len(text),text.replace('ほきん','平和')))
        self.assertFalse(CR._changed_genitive_object_allowed(text,0,len(text),
            text.replace('としょかんでかりたほきん','みせでかったほん')))

    def test_multiple_slips_and_punctuation_offsets(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
            ('としょかんでかりたほきんをかえして、やさいをこまかくきすります。',
             'としょかんでかりたほんをかえして、やさいをこまかくきります。'),
            ('としょかんでかりたほきんをかえしてから、しりょうをめーるでおきります。',
             'としょかんでかりたほんをかえしてから、しりょうをめーるでおくります。'),
            ('😀、やさいをこまかくきすります。','😀、やさいをこまかくきります。'),
        ):
            for comma in ('、',','):
                original=text.replace('、',comma)
                result=app.correct_line(original,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(self.reading(result['corrected']),expected.replace('、',comma),original)
                self.assertEqual(result.get('odd_spans'),[],original)

    def test_normal_relations_and_explicit_examples_remain_literal(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('としょかんでかりたほんをかえして、やさいをこまかくきります。',
                     'しりょうを、めーるでおくります。','やさいを、こまかくきります。',
                     '資料を、返還します。','この制度は、必要です。',
                     '「としょかんでかりたほきんをかえして、やさいをこまかくきすります」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)

    def test_physical_and_user_stops_survive_a_second_repair(self):
        import app
        from decisions import DecisionStore
        from tests_analysis_async import initial
        a=initial()
        for noun in ('ほんん','ほこん'):
            prefix='としょかんでかりた'+noun+'をかえして、'
            text=prefix+'やさいをこまかくきすります。'
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],prefix+'やさいをこまかくきります。')
        ledger=DecisionStore();ledger.protect('ほきん')
        text='としょかんでかりたほきんをかえして、やさいをこまかくきすります。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=ledger)
        self.assertEqual(result['corrected'],text.replace('きすります','きります'))


if __name__=='__main__':unittest.main()
