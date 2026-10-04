# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
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

    def test_native_adverb_keeps_an_expressive_finite_tail(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('こうおもいますぅ','こう思いますぅ','ゆっくりよみまぁす。',
                     'ゆっくり読みまぁす。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('こうおもいまぇ','こうおもいまぁ','しらゆほおもいますぅ',
                     'りんごをよみますぅ','こうおもいまぅす'):
            self.assertFalse(R.native_prolonged_clause(text),text)

    def test_prolonged_adverb_proves_only_its_original_word_and_edge(self):
        for source,span in (('猫がふぅっと息を吐く。',(2,6)),
                            ('風がさぁっと吹いた。',(2,6)),
                            ('ふぅーっと息を吐く。',(0,5))):
            self.assertIn(span,R.native_prolonged_adverb_ranges(source))
            self.assertIn(span,R.native_context_ranges(source))
        for source in ('猫がふぃっと息を吐く。','しらゆほぅっと息を吐く。',
                       'ふぅっ','ふぅ。っと息を吐く。'):
            self.assertFalse(R.native_prolonged_adverb_ranges(source),source)
        source='猫がふぅっと、しらゆほます。'
        self.assertEqual(R.native_prolonged_adverb_ranges(source),((2,6),))
        # No source token edge is invented inside a swallowed unknown word.
        self.assertFalse(R.native_prolonged_adverb_ranges('猫がふぅっとしらゆほます。'))
        self.assertFalse(any(a<=6 and b>=len(source)-1 for a,b in R.native_context_ranges(source)))

    def test_written_clause_keeps_prolonged_adverb_without_false_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for source in ('猫がふぅっと息を吐く。','風がさぁっと吹いた。',
                       'ふぅーっと息を吐く。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'),source)
        self.assertEqual(a.store.revision(),revision)

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
                assert_reviewed_source_spelling(self, r['corrected'], text);self.assertEqual(r['odd_spans'],[])
        for bad in ('このはこをまどのちかくにおきまぅす。',
                    'このはこをまどのちかくにおきまぃす。'):
            r=app.correct_line(bad,a.store,dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None,input_method='kana')
            assert_repaired_spelling(self, r, 'このはこをまどのちかくにおきます。')

if __name__=='__main__':unittest.main()

