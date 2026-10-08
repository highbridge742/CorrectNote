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
    def test_native_okurigana_variants_are_not_different_senses(self):
        with patch('ime_language._factory',None):
            for source,wanted in (
                    ('物をとりだします。','物を取り出します。'),
                    ('箱から資料をとりだします。','箱から資料を取り出します。'),
                    ('箱からとりだします。','箱から取り出します。')):
                with self.subTest(source=source):
                    self.assertEqual(self.project(source),wanted)
            # Different kanji and lexical senses still need independent proof.
            for text in ('すこしおくれました','時間をかえます','天気をとりだします。'):
                with self.subTest(source=text):self.assertIsNone(self.project(text))
            with patch('last_choice.surface_for_reading',side_effect=lambda rd:'取出し' if rd=='とりだし' else None):
                self.assertEqual(self.project('物をとりだします。'),'物を取出します。')

    def test_literal_kana_meaning_survives_reverse_spelled_homophones(self):
        with patch('ime_language._factory',None):
            for source,wanted in (
                    ('ものをはこにいれます。','ものを箱に入れます。'),
                    ('ものだけをはこにいれます。','ものだけを箱に入れます。'),
                    ('ひつようなものだけをはこにいれておきます。','必要なものだけを箱に入れておきます。'),
                    ('はこにいれたものをとりだします。','箱に入れたものを取り出します。'),
                    ('ものをとりだします。','ものを取り出します。'),
                    ('ものを招待します。','者を招待します。')):
                with self.subTest(source=source):
                    r=self.run_line(source)
                    self.assertEqual(r['corrected'],wanted)
                    self.assertFalse(r['odd_spans'])
                    self.assertEqual(r['analysis_status'],'complete')
            # The meaning of an unclassified noun cannot come from its
            # guessed spelling. No normal clause is marked as an error.
            for text in ('ぷねらをとりだします。','天気をとりだします。'):
                with self.subTest(source=text):self.assertIsNone(self.project(text))

    def test_focus_boundary_does_not_choose_an_unassessed_short_noun_sense(self):
        import reading_segments as R, kango_tier as K
        for face in ('桃','股','腿'):
            self.assertIn(face,R.native_lexical_reading_faces('もも'))
        self.assertIsNone(K.usage_tier_for_reading('腿','もも'))
        for text in ('ももだけにします。','ももばかりにします。','ももなどにします。',
                     '桃だけにします。','腿だけにします。','「ももだけ」と入力します。',
                     'ももだけにします。\t資料を保存します。'):
            with self.subTest(source=text):
                r=self.run_line(text)
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')

    def test_focus_ambiguity_keeps_independent_words_and_valid_choice(self):
        # The earlier discarded global tier change stopped these ordinary
        # spellings and selected an unproved person sense. Keep that evidence
        # distinct from the new focus boundary's unresolved interpretation.
        for source,expected in (('くつを履きます。','靴を履きます。'),
                                ('でんしゃに乗ります。','電車に乗ります。'),
                                ('いしを選びます。','いしを選びます。'),
                                ('ねこだけを見ます。','猫だけを見ます。')):
            with self.subTest(source=source):
                r=self.run_line(source)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'桃' if rd=='もも' else None):
            self.assertEqual(self.project('ももだけにします。'),'桃だけにします。')
        with patch('corrector._check_replacement',return_value=(None,'test_reject_shared_gate')):
            self.assertIsNone(self.project('ねこだけを見ます。'))

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