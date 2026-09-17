# -*- coding: utf-8 -*-
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('冊'),'requires native dictionary')
class CountedNominalTests(unittest.TestCase):
    def test_ordinals_preserve_whole_native_reading_and_do_not_become_quantities(self):
        for reading,face in (('さんさつめ','三冊目'),('ふたりめ','二人目'),
                             ('にだいめ','二台目'),('ひとつめ','一つ目')):
            with self.subTest(reading=reading):
                self.assertIn(face,R.native_ordinal_readings()[reading])
                self.assertIn(face,R.native_nominal_phrase_faces(reading))
                self.assertNotIn(reading,R.native_counter_readings())
                self.assertNotIn('quantity',S.nominal_roles(face))
        for text in ('はんさつめ','さんさつはんめ','とおめ','さんさつめめ','しらゆほめ'):
            self.assertNotIn(text,R.native_ordinal_readings())

    def test_units_have_independent_meaning_and_original_case(self):
        for text in ('三冊','さんさつ','三冊目','さんさつめ','半冊'):
            with self.subTest(text=text):self.assertIn('text',S.nominal_roles(text))
        self.assertIn('device',S.nominal_roles('にだいめ'))
        self.assertIn('person',S.nominal_roles('二人目'))
        self.assertIn('quantity',S.nominal_roles('二冊'))
        for text in ('二本','二枚','二個','二つ','しらゆほ冊'):
            with self.subTest(text=text):self.assertNotIn('text',S.nominal_roles(text))
        for text in ('さんさつをよみます','さんさつめをよみます','にさつにわけます',
                     'ほんをにさつにわけます','ふたりめにてがみをわたします'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,require_nominal=True,
                    require_object_fit=True))
        for text in ('さんさつめをよみんす','さんさつめめをよみます','にほんをよみます'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_clause(text,require_nominal=True,
                    require_object_fit=True))

    def test_normal_and_adjacent_repairs_share_counted_noun_evidence(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('さんさつめをよみます。','さんさつめをよみます。'),
            ('ほんをにさつにわけます。','ほんをにさつにわけます。'),
            ('ふたりめにてがみをわたします。','ふたりめにてがみをわたします。'),
            ('さんさつめをよみんす。','さんさつめをよみます。'),
            ('にだいめをつやいます。','にだいめをつかいます。'),
            ('二枚目は俳優です。','二枚目は俳優です。'),
            ('一つ目の妖怪です。','一つ目の妖怪です。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
