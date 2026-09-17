# -*- coding: utf-8 -*-
import unittest
import morphology as M
import contextual_repair as C
import reading_segments as R

@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class OriginalCaseStyleTests(unittest.TestCase):
    def test_counter_restoration_retains_original_nominal_case(self):
        for text in ('こどもにほんをよんでもらいます','せんせいにほんをよんでもらいます'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,True,True,True))
                self.assertTrue(any(t.surface=='に' and t.pos=='助詞' for t in M.tokenize(text)))
        for text in ('ほんをにさつよみます','かみをさんまいかさねます'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,True,True,True))

    def test_original_frame_supplies_style_for_every_candidate_path(self):
        import corrector
        from tests_analysis_async import initial
        a=initial();tk=corrector.make_tokenizer(a.store)
        text='まどをしめてからほんをよみんす'
        for kind in ('kana_predicate','lexical','auxiliary_connection'):
            target=C.RepairTarget(text,11,len(text),0,len(text),(),True,'',kind)
            self.assertTrue(C._source_predicate_context(target,tk))
        text='よみんす'
        target=C.RepairTarget(text,0,len(text),0,len(text),(),True,'','lexical')
        self.assertFalse(C._source_predicate_context(target,tk))

    def test_later_clause_repairs_keep_original_kana_and_earlier_object(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('まどをしめてからほんをよみんす。','まどをしめてからほんをよみます。'),
            ('まどをしめてからほんをよみまもす。','まどをしめてからほんをよみます。'),
            ('てがみをかいてから゛んをよみます。','てがみをかいてからほんをよみます。'),
            ('こどもにほんをよんでもらいます。','こどもにほんをよんでもらいます。')):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],expected);self.assertEqual(r['odd_spans'],[])

if __name__=='__main__':unittest.main()

