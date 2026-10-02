# -*- coding: utf-8 -*-
"""Whole nominal readings use positive relations, not arbitrary noun splits."""
import unittest
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class NominalIMECompoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        import corrector
        cls.state=initial();cls.tokenize=staticmethod(corrector.make_tokenizer(cls.state.store))
    def test_dimension_action_and_document_purpose_are_shared(self):
        from semantic_roles import nominal_compound_support
        for left,right in (('高さ','固定'),('幅','固定'),('工事','資料'),('相談','資料'),('相談','記録')):
            with self.subTest(left=left,right=right):self.assertTrue(nominal_compound_support(left,right))
        for left,right in (('会期','毛'),('画面','繁栄'),('雪駄','帝'),('窓','資料'),('窓','記録')):
            with self.subTest(left=left,right=right):self.assertFalse(nominal_compound_support(left,right))
    def test_same_relation_explains_full_original_reading(self):
        from reading_segments import completed_native_reading
        for source in ('たかさこてい','はばこてい','こうじしりょう','そうだんしりょう'):
            with self.subTest(source=source):self.assertTrue(completed_native_reading(source))
        self.assertFalse(completed_native_reading('かいきけ'))
    def test_first_conversion_uses_the_original_whole_reading(self):
        from ime_spelling import project_first_words
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest(ime.error)
        a=self.state
        for source,expected in (('たかさこてい','高さ固定'),('はばこてい','幅固定'),('こうじしりょう','工事資料'),('そうだんしりょう','相談資料')):
            with self.subTest(source=source):
                result=project_first_words(source,a.store,a.dict_index,a.decisions,self.tokenize)
                self.assertIsNotNone(result);self.assertEqual(result[0],expected)
                self.assertTrue(M.native_spelling_only(source,result[0]))
        self.assertIsNone(project_first_words('かいきぜ',a.store,a.dict_index,a.decisions,self.tokenize))
    def test_whole_application_keeps_clean_written_compounds(self):
        import app
        a=self.state
        for source in ('高さ固定','工事資料','謝詞か','ちよ'):
            with self.subTest(source=source):
                result=app.correct_line(source+'\t',a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source+'\t')
    def test_unknown_noun_pairs_do_not_gain_lexical_protection(self):
        from reading_segments import native_lexical_phrase
        for source in ('会期毛','会期是','画面繁栄','木意義'):
            with self.subTest(source=source):self.assertFalse(native_lexical_phrase(source,self.tokenize))

if __name__=='__main__':unittest.main()