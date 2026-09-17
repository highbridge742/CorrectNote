# -*- coding: utf-8 -*-
"""A voicing transposition must not turn a mere reading key into a word."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import corrector as C


@unittest.skipUnless(M.dictionary_inflections('続き'),'requires native dictionary')
class MovedWordEvidenceTests(unittest.TestCase):
    def test_whole_lexical_identity_is_separate_from_reading_cost(self):
        for reading in ('つづき','まちかど','けしき','びっくり'):
            with self.subTest(reading=reading):self.assertTrue(R.native_lexical_reading_faces(reading))
        for reading in ('まどへ','まどつ','ぷねら','まどを'):
            with self.subTest(reading=reading):self.assertFalse(R.native_lexical_reading_faces(reading))
        self.assertIsNotNone(C._table_cost('まどへ'))

    def test_moved_mark_keeps_real_repairs_and_rejects_unproved_words(self):
        from tests_analysis_async import initial
        a=initial()
        self.assertEqual(C._moved_dakuten_fix('つつぎ',a.store,a.dict_index),'つづき')
        self.assertIsNone(C._moved_dakuten_fix('まとべ',a.store,a.dict_index))
        self.assertIsNone(C._moved_dakuten_fix('まとづ',a.store,a.dict_index))
        self.assertIsNone(C._moved_dakuten_fix('つづき',a.store,a.dict_index))
        with patch.object(a.store,'lookup',side_effect=lambda rd:[{'solid':True}] if rd=='まどへ' else []):
            self.assertEqual(C._moved_dakuten_fix('まとべ',a.store,a.dict_index),'まどへ')

    def test_application_never_uses_the_cost_only_nominal_candidates(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for wrong,bad in (('まとべ','まどへ'),('まとづ','まどつ')):
            text='へやの'+wrong+'をあけてくうきをいれかえます。'
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertNotEqual(result['corrected'],'へやの'+bad+'をあけてくうきをいれかえます。')
        for text in ('へやのまどをあけてくうきをいれかえます。','はなしのつづきをよみます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
