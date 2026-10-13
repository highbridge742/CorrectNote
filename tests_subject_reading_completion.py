# -*- coding: utf-8 -*-
"""Share actual nominative meaning proof with full native reading completion."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.HAS_JANOME, 'requires native dictionary')
class SubjectReadingCompletionTests(unittest.TestCase):
    def setUp(self):
        R.completed_native_reading_clause.cache_clear()
        R.completed_native_reading.cache_clear()

    def tearDown(self):
        R.completed_native_reading_clause.cache_clear()
        R.completed_native_reading.cache_clear()

    def test_actual_subject_and_same_predicate_share_existing_positive_roles(self):
        for source in ('しょるいがとどきます', 'がくせいがはなします'):
            with self.subTest(source=source):
                self.assertTrue(R.completed_native_reading_clause(source, require_object_fit=True))
                self.assertTrue(R.completed_native_reading_clause(source))
                self.assertTrue(R.completed_native_reading(source))

    def test_missing_subject_meaning_or_predicate_meaning_does_not_complete(self):
        for attribute in ('native_verb_roles', 'nominal_roles'):
            for source in ('しょるいがとどきます', 'がくせいがはなします'):
                with self.subTest(attribute=attribute, source=source):
                    R.completed_native_reading_clause.cache_clear()
                    with patch.object(S, attribute, return_value=frozenset()):
                        self.assertFalse(R.completed_native_reading_clause(source))

    def test_whole_subject_and_actual_source_case_remain_required(self):
        for source in ('しょるいがとどきます', 'がくせいがはなします'):
            for attribute in ('native_nominal_phrase_faces', 'native_nominal_case_boundary'):
                with self.subTest(attribute=attribute, source=source):
                    R.completed_native_reading_clause.cache_clear()
                    with patch.object(R, attribute, return_value=() if attribute.endswith('faces') else None):
                        self.assertFalse(R.completed_native_reading_clause(source))

    def test_unmatched_unknown_and_unfinished_constructions_add_no_proof(self):
        for source in ('しりょうがはなします', 'しょるいがはなします',
                       'がくせいがとどきます', 'ぷねらがはなします',
                       'しょるいがとどき', 'がくせいがはなし',
                       'しょるいがとどきますです', 'がくせいがはなしますです',
                       'しょるいがありた'):
            with self.subTest(source=source):
                self.assertFalse(R.completed_native_reading_clause(source))
                self.assertFalse(R.completed_native_reading(source))

    def test_same_field_and_predicate_are_not_borrowed_from_another_clause(self):
        for separator in ('。', '\t', '⇒', '→', '\n', '  ', ''):
            source='しりょうがはなします'+separator+'がくせいがはなします'
            with self.subTest(separator=separator):
                self.assertFalse(R.completed_native_reading_clause(source))
                self.assertFalse(R.completed_native_reading(source))

    def test_basic_original_grammar_is_not_replaced_by_meaning_catalogue(self):
        for source in ('しょるいがあります', 'がくせいがいます', 'みずがある'):
            with self.subTest(source=source):
                with patch.object(S, 'native_verb_roles', return_value=frozenset()):
                    self.assertTrue(R.completed_native_reading_clause(source))
        self.assertTrue(R.completed_native_reading_clause('しょるいをほぞんします'))
        self.assertTrue(R.completed_native_reading_clause('がくせいがべんきょうします'))


    def test_full_romaji_finishes_with_original_common_gate_and_partial_block(self):
        from correction_entry import correct_line
        import corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        self.addCleanup(set_active,None)
        def run(source,state):
            return correct_line(source,state.store,context_vocab={},input_method='romaji',
                dict_index=state.dict_index,decisions=state.decisions,context_vec=state.context_vec)
        source='shoruigatodokimasu';a=initial()
        row=run(source,a)
        self.assertEqual(row['corrected'],'書類が届きます')
        self.assertEqual(row['odd_spans'],[])
        self.assertEqual(row['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assertEqual(run(source,a)['corrected'],source)
        a.decisions.protect('ruigato')
        self.assertEqual(run(source,a)['corrected'],source)

    def test_full_romaji_keeps_code_and_explicit_quote_protection(self):
        from correction_entry import correct_line
        from tests_analysis_async import initial
        from last_choice import set_active
        self.addCleanup(set_active,None)
        for source in ('print( shoruigatodokimasu )', 'const gakuseigahanashimasu = 1;',
                       '「shoruigatodokimasu」と入力します。'):
            with self.subTest(source=source):
                a=initial()
                row=correct_line(source,a.store,context_vocab={},input_method='romaji',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=a.context_vec)
                self.assertEqual(row['corrected'],source)
                self.assertEqual(row['odd_spans'],[])
                self.assertEqual(row['analysis_status'],'complete')

if __name__ == '__main__':
    unittest.main()
