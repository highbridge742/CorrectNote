# -*- coding: utf-8 -*-
"""A native volitional ending does not alone prove a relative noun seam."""
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.HAS_JANOME,'requires native dictionary')
class VolitionalRelativeTests(unittest.TestCase):
    def test_volitional_is_finite_without_proving_a_relative_seam(self):
        for source in ('きよう','あけよう','よもう','ほぞんしよう','開けよう'):
            with self.subTest(source=source):
                self.assertFalse(R.native_attributive_predicate_end(source))
        for source in ('きよう','あけよう','よもう'):
            self.assertTrue(R.native_source_finite_verb(source),source)
        self.assertTrue(R.completed_sahen_reading('ほぞんしよう',allow_nonpolite=True))

    def test_case_cannot_borrow_a_noun_after_volition(self):
        for source in ('きようと','あけようと','よもうほん'):
            with self.subTest(source=source):
                self.assertFalse(R.native_adnominal_reading_parts(source,True))
        source='きようとにいきます'
        self.assertNotIn((0,len(source)),R.native_source_predicate_ranges(source))
        self.assertNotIn((0,5,('戸',)),R.native_argument_predicate_contexts(source))

    def test_lexical_u_and_conjectural_copula_keep_their_native_end(self):
        for source in ('かう','おもう','きる','あける','あけた','よんだ',
                       'あるだろう','くるだろう','ありし','よみける','せし'):
            with self.subTest(source=source):
                self.assertTrue(R.native_attributive_predicate_end(source))
        for source in ('あけると','あけたと','よんだほん','ひろいへや','しずかなへや'):
            self.assertTrue(R.native_adnominal_reading_parts(source,True),source)
        self.assertIn((0,9),R.native_source_predicate_ranges('きょうとにいきます'))

if __name__=='__main__':unittest.main()
