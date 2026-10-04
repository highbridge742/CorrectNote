# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
from unittest.mock import patch
import morphology

@unittest.skipUnless(morphology.HAS_JANOME,'requires native dictionary')
class SpellingSenseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial();cls.a.context_vec=None
    @classmethod
    def tearDownClass(cls):
        from last_choice import set_active
        set_active(None)
    def run_line(self,text):
        import app
        revision=self.a.store.revision()
        r=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(self.a.store.revision(),revision)
        return r
    def verify(self,pairs):
        for text,wanted in pairs:
            with self.subTest(text=text):
                r=self.run_line(text)
                assert_reviewed_source_spelling(self, r['corrected'], wanted)
                self.assertEqual(r.get('odd_spans'),[])
                again=self.run_line(wanted)
                assert_reviewed_source_spelling(self, again['corrected'], wanted)
                self.assertEqual(again.get('odd_spans'),[])
    def test_unresolved_senses_do_not_become_a_different_written_meaning(self):
        # Holding an unresolved reading is not completion of general spelling.
        self.verify((('じかんをかえます。','じかんをかえます。'),
                     ('時間をかえます。','時間をかえます。'),
                     ('日時をかえます。','日時をかえます。'),
                     ('めをさまします。','めをさまします。'),
                     ('目をさまします。','目をさまします。')))
    def test_supported_sense_and_already_written_words_keep_their_meaning(self):
        self.verify((('スープをさまします。','スープをさまします。'),
                     ('大きさをかえます。','大きさをかえます。'),
                     ('目を冷まします。','目を冷まします。'),
                     ('時間を替えます。','時間を替えます。')))
    def project(self,text):
        from kana_spelling import project
        revision=self.a.store.revision()
        result=project(text,self.a.store,self.a.dict_index,self.a.decisions)
        self.assertEqual(self.a.store.revision(),revision)
        return result[0] if result else None

    def test_projection_uses_the_unchanged_case_even_with_an_adverb(self):
        # Projection follows anomaly/closed-field admission; open kana above
        # stay literal. These are different public contracts.
        for source,wanted in (
                ('手紙をおくれます','手紙を送れます'),
                ('手紙をすぐおくれます','手紙をすぐ送れます'),
                ('本をゆっくりよめます','本をゆっくり読めます'),
                ('大きさをすぐかえます','大きさをすぐ変えます'),
                ('スープをゆっくりさまします','スープをゆっくり冷まします')):
            with self.subTest(source=source):
                self.assertEqual(self.project(source),wanted)
        for source in ('時間をすぐかえます','電車がおくれます','すこしおくれました'):
            with self.subTest(unresolved=source):
                self.assertIsNone(self.project(source))

    def test_explicit_spelling_is_not_overruled_by_automatic_ambiguity(self):
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'替え' if rd=='かえ' else None):
            self.assertEqual(self.project('時間をかえます'),'時間を替えます')
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'送れ' if rd=='おくれ' else None):
            self.assertEqual(self.project('すこしおくれました'),'すこし送れました')

if __name__=='__main__':unittest.main()