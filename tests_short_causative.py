# -*- coding: utf-8 -*-
"""Short causatives and the distinct interruption suffix share native evidence."""
import unittest
import morphology as M
import oddness as O


@unittest.skipUnless(M.dictionary_inflections('す'), 'requires native dictionary')
class ShortCausativeTests(unittest.TestCase):
    def test_irrealis_causative_and_continuative_interruption_are_distinct(self):
        def connection(left,right):
            return O._derivational_connection(M.dictionary_paradigms(left),
                M.dictionary_paradigms(right),'causative','動詞')
        for left,right in (('読ま','す'),('書か','す'),('食べ','さす'),
                           ('読み','さす'),('書か','せる'),('食べ','させる')):
            with self.subTest(left=left,right=right):self.assertIs(connection(left,right),True)
        for left,right in (('まき','す'),('書く','す'),('読み','す')):
            with self.subTest(left=left,right=right):self.assertIs(connection(left,right),False)
        self.assertIsNone(connection('しらゆほ','す'))

    def test_native_source_and_candidate_validation_reject_same_bad_connection(self):
        import corrector as C,contextual_repair as R
        from tests_analysis_async import initial
        a=initial();tok=C.make_tokenizer(a.store)
        text='このはこをまどのちかくにおきまきす。'
        anomalies=O.is_odd_run(text,tok,with_spans=True)
        self.assertIn(('まき','す',14,17),anomalies)
        self.assertNotIn(('この','は',0,3),anomalies)
        self.assertFalse(R._productive_predicate('まきす','まき'))
        self.assertTrue(R._productive_predicate('読ます','読ま'))
        # The native dictionary stores this interruption verb as one word.
        self.assertTrue(R._productive_predicate('読みさす','読みさす'))

    def test_application_keeps_normal_short_forms_and_repairs_intrusion(self):
        import app
        from tests_analysis_async import initial
        from kana_layout import single_key_drop_adjacency,single_key_drop_is_duplicate
        a=initial();a.context_vec=None
        for text in ('本を読ます。','子どもに本を読ます。','子どもに食べさす。',
                     '本を読みさす。','見聞きす。','上書きす。','手紙を書き記す。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],[])
        source='このはこをまどのちかくにおきまきす。'
        expected='このはこをまどのちかくにおきます。'
        self.assertTrue(single_key_drop_adjacency(source,expected))
        self.assertFalse(single_key_drop_is_duplicate(source,expected))
        result=app.correct_line(source,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],expected);self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
