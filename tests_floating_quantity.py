# -*- coding: utf-8 -*-
import unittest
import morphology as M
import reading_segments as R

@unittest.skipUnless(M.dictionary_inflections('半'),'requires native dictionary')
class FloatingQuantityTests(unittest.TestCase):
    def test_counter_prefix_is_independent_of_accidental_functional_parse(self):
        for text,cut in (('にさつかいます',3),('さんさつよみます',4),
                         ('はんさつよみます',4),('いっさつはんよみます',6)):
            with self.subTest(text=text):
                self.assertIn(cut,R.native_adverbial_reading_cuts(text))
                self.assertTrue(R.native_adverbial_predicate_reading(text))
        for text in ('またたびをたべます','ほどかします'):
            self.assertEqual(R.native_adverbial_reading_cuts(text),())
        self.assertFalse(R.native_adverbial_predicate_reading('ひとつばしのえきをつかいます'))

    def test_fractional_reading_uses_native_half_and_never_recurses(self):
        readings=R.native_counter_readings()
        for text,face in (('はんさつ','半冊'),('はんまい','半枚'),('はんこ','半個'),
                          ('いっさつはん','一冊半'),('にこはん','二個半')):
            self.assertIn(face,readings[text])
        self.assertNotIn('いっさつはんはん',readings)
        self.assertFalse(R.completed_native_reading_clause('ほんをにさつよむます',require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('しらゆほをにさつよみます',require_object_fit=True))

    def test_quantity_range_does_not_certify_unknown_or_unfinished_predicate(self):
        text='ほんをにさつしらゆほます。'
        ranges=R.native_context_ranges(text)
        self.assertIn((0,6),ranges)
        self.assertFalse(any(start<=0 and end>=len(text)-1 for start,end in ranges))
        self.assertFalse(R.native_adverbial_predicate_reading('にさつしらゆほます'))

    def test_normal_fractional_and_unfinished_source_survive_application(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('ほんをにさつかいます。','ほんをさんさつよみます。',
                     'ほんをはんさつよみます。','はんさつのほんをよみます。',
                     'ほんをいっさつはんよみます。','ほんをにさつかいまあ。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],[])
        text='ほんをにさつしらゆほます。'
        r=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(r['corrected'],text);self.assertTrue(r['odd_spans'])

@unittest.skipUnless(M.dictionary_inflections('半'),'requires native dictionary')
class OrdinaryQuantityMeaningTests(unittest.TestCase):
    def test_native_food_and_material_meanings_do_not_transfer_to_homophones(self):
        import semantic_roles as S
        for word in ('林檎','リンゴ','りんご','蜜柑','ミカン','みかん','苺','イチゴ','いちご','バナナ'):
            self.assertTrue(M.dictionary_inflections(word))
            self.assertTrue(S.support(word,'食べる'))
            self.assertFalse(S.support(word,'読む'))
        self.assertTrue(S.support('辞書','買う'))
        self.assertTrue(S.support('紙','重ねる'))
        self.assertTrue(S.support('資料','重ねる'))
        self.assertFalse(S.support('紙','飲む'))
        self.assertFalse(S.nominal_roles('しらゆほ'))

    def test_normal_quantity_food_and_material_sentences_keep_text(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('じしょをにさつかいます。','りんごをさんこたべます。',
                     'みかんをさんこたべます。','ばななをさんぼんたべます。',
                     'いちごをさんこかいます。','かみをさんまいかさねます。',
                     'しりょうをにまいかさねます。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],[])

if __name__=='__main__':unittest.main()

