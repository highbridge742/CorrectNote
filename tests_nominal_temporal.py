# -*- coding: utf-8 -*-
"""A source adjunct edge does not approve its unexplained following text."""
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('前'), 'requires native dictionary')
class NominalTemporalTests(unittest.TestCase):
    def test_nominal_reading_and_both_particles_are_required(self):
        for text in ('かいもののまえに','しょくじのあとに','かいぎののちに',
                     'つくえのまえに','もののまえに'):
            with self.subTest(text=text):self.assertTrue(R.native_nominal_temporal_prefix(text))
        for text in ('ぷねらのまえに','かいものまえに','かいもののまえを',
                     'かいもののぜんに','かいもののごに','のまえに',
                     'かったのまえに','かうのあとに','かいもののまえには'):
            with self.subTest(text=text):self.assertFalse(R.native_nominal_temporal_prefix(text))

    def test_same_edge_exposes_only_the_actual_following_nominal_frame(self):
        text='かいもののまえにさいふをたしかめます'
        self.assertIn(8,R.native_adverbial_reading_cuts(text))
        self.assertIn((8,12,('財布',)),R.native_object_predicate_contexts(text))
        self.assertIn((8,12),R.native_context_ranges(text))
        text='しょくじのあとにしりょうをよみます'
        self.assertIn(8,R.native_adverbial_reading_cuts(text))
        self.assertIn((8,13),R.native_context_ranges(text))

    def test_adjunct_does_not_certify_unknown_nouns_or_broken_predicates(self):
        for text in ('かいもののまえにぷねらをたしかめます',
                     'かいもののまえにさいふをたしかます'):
            with self.subTest(text=text):
                self.assertFalse(R.intact_native_reading(text))
                self.assertNotIn((0,len(text)),R.native_context_ranges(text))
        self.assertNotIn(9,R.native_adverbial_reading_cuts('ぷねらもののまえにさいふをたしかめます'))

    def test_application_retains_normal_source_without_false_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('かいもののまえにさいふをたしかめます。',
                     'しょくじのあとにしりょうをよみます。',
                     'つくえのまえにほんをならべます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
