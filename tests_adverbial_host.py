# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('年末'),'requires native dictionary')
class AdverbialHostTests(unittest.TestCase):
    def test_original_continuative_owns_an_inner_adverb_before_broken_tail(self):
        from morphology import preserves_native_adverbial_word
        from pos_grammar import unexplained_shifted_predicate_tails
        for source,changed in (('ふでをあらいまぇ。','ふでを洗います。'),
                               ('かおをぬぐいまぇ。','かおを拭います。')):
            with self.subTest(source=source):
                self.assertTrue(unexplained_shifted_predicate_tails(source))
                self.assertTrue(preserves_native_adverbial_word(source,changed))
        for source,changed in (('いまぇ','います'),
                               ('今は洗います。','居間は洗います。')):
            with self.subTest(source=source):
                self.assertFalse(preserves_native_adverbial_word(source,changed))

    def test_bound_readings_do_not_supply_free_adverbs(self):
        for face,reading in S.DEPENDENT_TEMPORAL_READINGS:
            with self.subTest(face=face,reading=reading):
                self.assertNotIn(face,R._native_adverbial_faces(reading))
        for reading,face in (('ねんまつ','年末'),('げつまつ','月末'),('しゅうまつ','週末'),
                             ('いま','今'),('ごご','午後'),('いご','以後')):
            with self.subTest(reading=reading):
                self.assertIn(face,R._native_adverbial_faces(reading))
        self.assertFalse(R.completed_native_reading_clause('ほんをまつつかいます',
            require_nominal=True,require_object_fit=True))

    def test_degree_modifier_does_not_certify_an_arbitrary_nominal_clause(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for face,reading in S.DEPENDENT_DEGREE_READINGS:
            self.assertNotIn(face,R._native_adverbial_faces(reading))
        malformed='ごくごじてんをよみます。'
        self.assertFalse(R.intact_native_reading(malformed))
        result=app.correct_line(malformed,a.store,dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions,input_method='kana')
        self.assertTrue(result['odd_spans'])
        for text in ('ごくちいさいはこをつかいます。','ごくまれにほんをよみます。',
                     'ごくわずかなみずをのみます。','ごくふつうのはなしです。'):
            result=app.correct_line(text,a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result['odd_spans'],text)

    def test_native_whole_word_can_span_a_short_functional_prefix(self):
        for text,cut in (('ねんまつかいます',4),('げつまつかいます',4),
                         ('しゅうまつかいます',5),('にさつかいます',3)):
            with self.subTest(text=text):self.assertIn(cut,R.native_adverbial_reading_cuts(text))
        self.assertNotIn(2,R.native_adverbial_reading_cuts('ほどかします'))
        self.assertNotIn(2,R.native_adverbial_reading_cuts('まつつかいます'))

    def test_source_normal_and_adjacent_candidate_use_the_same_proof(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('ほんをねんまつかいます。','ほんをねんまつかいます。'),
            ('ほんをげつまつかいます。','ほんをげつまつかいます。'),
            ('ほんをにつつかいます。','ほんをにさつかいます。'),
            ('ほんをにつつよみます。','ほんをにさつよみます。'),
            ('薬を末にします。','薬を末にします。'),
            ('中の大きさを選びます。','中の大きさを選びます。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                assert_reviewed_result_spelling(self, result, expected)
                self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
