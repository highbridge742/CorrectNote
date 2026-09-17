# -*- coding: utf-8 -*-
import unittest
import morphology as M
import reading_segments as R

@unittest.skipUnless(M.dictionary_inflections('ます'),'requires native dictionary')
class ProlongedClauseTests(unittest.TestCase):
    def test_same_vowel_needs_a_whole_native_predicate_and_argument_fit(self):
        for text in ('いまぁす','たべまぁす','よみまぁす','りんごをさんこたべまぁす',
                     'このはこをまどのちかくにおきまぁす'):
            with self.subTest(text=text):self.assertTrue(R.native_prolonged_clause(text))
        for text in ('おきまぅす','おきまぃす','しらゆほまぁす',
                     'りんごをよみまぁす','かいまぁ'):
            with self.subTest(text=text):self.assertFalse(R.native_prolonged_clause(text))

    def test_same_source_ranges_preserve_voice_but_not_following_unknown(self):
        text='いまぁす。しらゆほます。'
        ranges=R.native_context_ranges(text)
        self.assertIn((0,4),ranges)
        self.assertFalse(any(a<=5 and b>=len(text)-1 for a,b in ranges))

    def test_application_keeps_prolongation_and_repairs_different_vowel_intrusion(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('いまぁす。','たべまぁす。','りんごをさんこたべまぁす。',
                     'このはこをまどのちかくにおきまぁす。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],[])
        for bad in ('このはこをまどのちかくにおきまぅす。',
                    'このはこをまどのちかくにおきまぃす。'):
            r=app.correct_line(bad,a.store,dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None,input_method='kana')
            self.assertEqual(r['corrected'],'このはこをまどのちかくにおきます。')

if __name__=='__main__':unittest.main()

