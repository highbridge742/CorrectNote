# -*- coding: utf-8 -*-
"""Native grammar can retain a source without certifying a candidate's meaning."""
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('決する'), 'requires native dictionary')
class UnclassifiedNativeTests(unittest.TestCase):
    def test_complete_unclassified_verbs_protect_source_spelling(self):
        for text in ('かんがえてはけっします', 'なやんではけっします',
                     'かいてはけっします', 'てがみをかいてはけっします',
                     'したためてはながめます', 'たたずんではおもいます',
                     'かんがえてはまよいます'):
            with self.subTest(text=text):
                self.assertTrue(R.intact_native_reading(text))
                self.assertTrue(R.completed_native_reading_sequence(text, allow_unclassified=True))
        self.assertTrue(R.completed_native_verb_reading('けっします', require_roles=False))
        self.assertFalse(R.completed_native_verb_reading('けっします'))

    def test_bad_inflection_unknown_stems_and_incompatible_objects_are_not_proved(self):
        for text in ('かくてはけします', 'よみではかきます',
                     'かいてはけっしま', 'かいてはけっするます',
                     'かいてはけっしますです', 'かいてはしらゆほます',
                     'かいてはけしなます', 'りんごをよんではけっします',
                     'ほんをたべてはけっします'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_sequence(text, allow_unclassified=True))
        self.assertFalse(R.completed_native_reading_link('かんがえては',
            require_nominal=True, allow_unclassified=True))

    def test_candidate_object_proof_still_requires_semantic_fit(self):
        self.assertFalse(R.completed_native_link_clause('けっします'))
        self.assertFalse(R.completed_native_reading_sequence('てがみをかいてはけっします'))
        self.assertFalse(R.native_object_predicate_proof('てがみをかいてはけっします', 4, ('手紙',)))
        self.assertTrue(R.native_object_predicate_proof('てがみをかいてはけします', 4, ('手紙',)))

    def test_application_preserves_normal_text_and_existing_adjacent_repairs(self):
        import app
        from tests_analysis_async import initial
        a = initial(); a.context_vec = None
        for text, expected in (
                ('かんがえてはけっします。', 'かんがえてはけっします。'),
                ('なやんではけっします。', 'なやんではけっします。'),
                ('てがみをかいてはけっします。', 'てがみをかいてはけっします。'),
                ('かいてはけしなます。', 'かいては消します。'),
                ('ふでをあらいんす。', 'ふでをあらいます。'),
                ('会議の日程を長生します。', '会議の日程を調整します。'),
                ('もんじにゅうりょく。', 'もんじにゅうりょく。')):
            with self.subTest(text=text):
                result = app.correct_line(text, a.store, input_method='kana',
                    dict_index=a.dict_index, context_vec=None, decisions=a.decisions)
                self.assertEqual(result['corrected'], expected)
                self.assertEqual(result.get('odd_spans'), [])


if __name__ == '__main__':
    unittest.main()
