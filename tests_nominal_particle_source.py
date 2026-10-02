# -*- coding: utf-8 -*-
"""Known noun phrases keep their original source spelling at a particle."""
import unittest,morphology
from reading_segments import native_lexical_phrase

@unittest.skipUnless(morphology.HAS_JANOME,'native dictionary')
class NominalParticleSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        import corrector
        cls.state=initial();cls.tokenize=staticmethod(corrector.make_tokenizer(cls.state.store))
    def test_written_compound_and_exact_kana_noun_before_particle(self):
        for text in ('謝詞か','謝詞','しゃしか','けんさか','けんさに','連絡資料も','書面通知か'):
            with self.subTest(text=text):self.assertTrue(native_lexical_phrase(text,self.tokenize))
    def test_predicate_or_particle_seam_is_not_a_nominal_phrase(self):
        for text in ('書きますか','けんかにに','資料が歩く','読んでを','静かなに','画面繁栄','雪駄帝','木意義','会期毛','会期背','会期是','剣素柵結果'):
            with self.subTest(text=text):self.assertFalse(native_lexical_phrase(text,self.tokenize))
    def test_interjection_and_na_adnominal_remain_available(self):
        for text in ('ああ','静かな'):
            with self.subTest(text=text):self.assertTrue(native_lexical_phrase(text,self.tokenize))
    def test_normal_phrase_survives_full_correction_without_purple(self):
        import app
        a=self.state
        for source in ('謝詞か','しゃしか','けんさか','連絡資料も'):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source);self.assertFalse(result.get('odd_spans'))

    def test_intact_column_does_not_disable_repair_in_another_column(self):
        import app,corrector
        a=self.state;source='謝詞か\tふあいるをひらきます'
        self.assertEqual(corrector._open_odd_single_kanji('謝詞か',self.tokenize),[])
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'謝詞か\tファイルを開きます')

if __name__=='__main__':unittest.main()
