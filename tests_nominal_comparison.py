# -*- coding: utf-8 -*-
"""Native comparison arguments must preserve their noun and completed predicate."""
import unittest
import morphology
from reading_segments import completed_native_nominal_predicate


@unittest.skipUnless(morphology.HAS_JANOME,'Requires the native dictionary')
class NominalComparisonTests(unittest.TestCase):
    def test_native_argument_and_same_finite_predicate(self):
        for text in ('このずとおなじです','このずとおなじだった',
                     'もとのずとおなじでした','このずとおなじなのです',
                     'このずとおなじものです'):
            with self.subTest(text=text):self.assertTrue(completed_native_nominal_predicate(text))

    def test_no_comparison_proof_for_an_extra_glyph_or_broken_tail(self):
        for text in ('このずとえおなじです','このずとあおなじだった',
                     'このずとおなじだます','このずとおなじかった',
                     'このずとおなじく','このずとあのず',
                     'このずにおなじです','このずをおなじです'):
            with self.subTest(text=text):self.assertFalse(completed_native_nominal_predicate(text))

    def test_written_argument_keeps_its_original_case(self):
        # Written short heads remain on their existing source path; this
        # extension does not create an alternative boundary for them.
        from tests_analysis_async import initial
        import app
        a=initial();text='この図と同じでした'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],text)
        self.assertFalse(result.get('odd_spans'))
        self.assertFalse(completed_native_nominal_predicate('この図を同じでした',allow_written=True))
        self.assertFalse(completed_native_nominal_predicate('この図とえ同じでした',allow_written=True))

    def test_normal_source_loses_only_its_false_anomaly(self):
        from tests_analysis_async import initial
        import app
        a=initial()
        for text in ('このずとおなじだった','もとのずとおなじでした'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result.get('odd_spans'))


if __name__=='__main__':unittest.main()
