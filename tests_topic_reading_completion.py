# -*- coding: utf-8 -*-
"""Keep actual topic particles when sharing existing subject meaning proof."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.HAS_JANOME, 'requires native dictionary')
class TopicReadingCompletionTests(unittest.TestCase):
    def setUp(self):
        R.completed_native_reading_clause.cache_clear()
        R.completed_native_reading.cache_clear()

    tearDown = setUp

    def test_existing_subject_roles_complete_actual_topic_and_focus(self):
        for source in ('しょるいはとどきます', 'がくせいもはなします',
                       'しょるいもとどきます', 'がくせいはいます',
                       'しょるいもあります', 'がくせいもはなしません',
                       'しょるいはとどきません'):
            with self.subTest(source=source):
                self.assertTrue(R.completed_native_reading_clause(source))
                self.assertTrue(R.completed_native_reading_clause(source, require_object_fit=True))
                self.assertTrue(R.completed_native_reading(source))

    def test_added_proof_needs_original_noun_case_and_both_meanings(self):
        for source in ('しょるいはとどきます', 'がくせいもはなします'):
            for module, attribute, empty in (
                (S, 'native_verb_roles', frozenset()),
                (S, 'nominal_roles', frozenset()),
                (R, 'native_nominal_phrase_faces', ()),
                (R, 'native_nominal_case_boundary', None),
            ):
                with self.subTest(source=source, attribute=attribute):
                    R.completed_native_reading_clause.cache_clear()
                    with patch.object(module, attribute, return_value=empty):
                        self.assertFalse(R.completed_native_reading_clause(source))

    def test_subject_proof_preserves_literal_topic_particle_and_positions(self):
        helper = R._native_nominal_functional_tail
        seen = []
        def trace(parts, *args, **kwargs):
            if kwargs.get('content_subject_faces'):
                seen.append((parts[0][0], parts[0][3:5],
                             kwargs['content_subject_faces'], kwargs.get('source_prefix')))
            return helper(parts, *args, **kwargs)
        with patch.object(R, '_native_nominal_functional_tail', side_effect=trace):
            self.assertTrue(R.completed_native_reading_clause('しょるいはとどきます'))
            self.assertTrue(R.completed_native_reading_clause('がくせいもはなします'))
        self.assertIn(('は', (4, 5), ('書類',), 'しょるい'), seen)
        self.assertIn(('も', (4, 5), ('学生',), 'がくせい'), seen)

    def test_unmatched_unfinished_and_nominal_interior_add_no_subject_proof(self):
        for source in ('しりょうははなします', 'しりょうもはなします',
                       'がくせいはとどきます', 'ぷねらははなします',
                       'ぷねらもはなします', 'しょるいはとどき',
                       'がくせいもはなしますです', 'せいははなします',
                       'せいもはなします'):
            with self.subTest(source=source):
                self.assertFalse(R.completed_native_reading_clause(source))
                self.assertFalse(R.completed_native_reading(source))

    def test_topic_does_not_borrow_a_different_subject_or_field(self):
        for source in ('がくせいはしょるいがよみます',
                       'しょるいはがくせいがはなします',
                       'がくせいはしょるいがとどきます',
                       'がくせいもがくせいもはなします',
                       'しょるいもがくせいもはなします'):
            with self.subTest(source=source):
                self.assertFalse(R.completed_native_reading_clause(source))
        for separator in ('。', '\t', '⇒', '→', '\n', '  ', ''):
            source = 'しりょうははなします' + separator + 'がくせいもはなします'
            with self.subTest(separator=separator):
                self.assertFalse(R.completed_native_reading_clause(source))
                self.assertFalse(R.completed_native_reading(source))
        self.assertTrue(R.completed_native_reading_clause('しょるいはがくせいがよみます'))
        self.assertTrue(R.completed_native_reading('しょるいはとどきますががくせいもはなします'))

    def test_existing_nominative_object_and_nominal_readings_stay_available(self):
        for source in ('しょるいがとどきます', 'がくせいがはなします',
                       'しょるいをほぞんします', 'もじがとどきます'):
            with self.subTest(source=source):
                self.assertTrue(R.completed_native_reading_clause(source))


if __name__ == '__main__':
    unittest.main()
