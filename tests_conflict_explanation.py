# -*- coding: utf-8 -*-
"""Purple explanations describe the actual predicate class, not another rule."""
import unittest
import morphology as M
import oddness as O


@unittest.skipUnless(M.dictionary_inflections('生産'),'requires native dictionary')
class ConflictExplanationTests(unittest.TestCase):
    def test_native_source_diagnostic_describes_the_class_that_rejected_it(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text,predicate,required,excluded in (
                ('日程を長生します。','長生','生物','費用'),
                ('資料を生存します。','生存','生物','製造'),
                ('交通費を生産します。','生産','費用','生物')):
            with self.subTest(text=text):
                reasons={}
                O.is_odd_run(text,tokenize,with_spans=True,store=a.store,
                    dict_index=a.dict_index,complete_line=True,reading_reasons_out=reasons)
                span=(text.index(predicate),text.index(predicate)+len(predicate))
                self.assertIn(span,reasons)
                self.assertIn(required,reasons[span])
                self.assertNotIn(excluded,reasons[span])


if __name__=='__main__':unittest.main()
