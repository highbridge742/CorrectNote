# -*- coding: utf-8 -*-
"""The exact original topic proof must also hold for the final verb spelling."""
import unittest
from unittest.mock import patch
import morphology as M
import semantic_roles as S


class DictionaryIME:
    def reverse_words(self, surface):
        reading = ''; units = []
        for token in M.tokenize(surface):
            start = len(reading)
            reading += token.reading
            units.append((token.start, token.end, start, len(reading), 0, 0))
        return reading, tuple(units)

    def phonetic(self, surface):
        return self.reverse_words(surface)[0]


class NoSearch:
    available = False
    def __enter__(self): return self
    def __exit__(self, *args): pass


@unittest.skipUnless(M.HAS_JANOME, 'requires native dictionary')
class TopicIMEProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        import corrector
        cls.state = initial()
        cls.tokenize = staticmethod(corrector.make_tokenizer(cls.state.store))

    @classmethod
    def tearDownClass(cls):
        from last_choice import set_active
        set_active(None)

    def alternatives(self, source, first, reading, enabled=True):
        from ime_homophone import positive_predicate_alternatives
        with patch('ime_candidates.SearchCandidates', return_value=NoSearch()):
            return positive_predicate_alternatives(source, first, reading,
                self.tokenize, DictionaryIME(), subject_completion=enabled)

    def test_direct_topic_is_opt_in_and_preserves_actual_particle_boundary(self):
        for source, verb_start in (('学生もはなします', 3), ('学生ははなします', 3)):
            self.assertEqual(S.subject_before(source, verb_start, self.tokenize), '')
            self.assertEqual(S.subject_before(source, verb_start, self.tokenize,
                allow_direct_topic=True), '学生')
        for source, verb_start in (('学生しかはなします', 4), ('学生も はなします', 4),
                                   ('学生のはなします', 3)):
            self.assertEqual(S.subject_before(source, verb_start, self.tokenize,
                allow_direct_topic=True), '')

    def test_same_subject_proof_selects_native_spelling_without_search(self):
        for tail in ('ます', 'ません'):
            rows = self.alternatives('学生もはなし' + tail, '学生も離し' + tail,
                                     'がくせいもはなし' + tail)
            self.assertEqual([row[0] for row in rows], ['学生も話し' + tail])
            self.assertEqual(rows[0][2]['subject'], '学生')
            self.assertEqual(rows[0][2]['shared_roles'], ['person'])
        self.assertEqual(self.alternatives('学生もはなします', '学生も離します',
            'がくせいもはなします', enabled=False), ())

    def test_changed_subject_and_missing_original_proof_cannot_lend_meaning(self):
        self.assertEqual(self.alternatives('資料もはなします', '学生も離します',
            'がくせいもはなします'), ())
        self.assertEqual(self.alternatives('資料もはなします', '資料も離します',
            'しりょうもはなします'), ())
        original = S.subject_candidate_evidence
        def without_source(subject, surface, following):
            return None if surface == 'はなします' else original(subject, surface, following)
        with patch.object(S, 'subject_candidate_evidence', side_effect=without_source):
            self.assertEqual(self.alternatives('学生もはなします', '学生も離します',
                'がくせいもはなします'), ())

    def test_existing_positive_first_spelling_is_not_replaced(self):
        self.assertEqual(self.alternatives('書類はとどきます', '書類は届きます',
            'しょるいはとどきます'), ())

    def test_full_romaji_completion_keeps_source_common_gate_and_partial_block(self):
        from correction_entry import correct_line
        from tests_analysis_async import initial
        from last_choice import set_active
        import corrector as C
        self.addCleanup(set_active, None)
        a = initial()
        def run(source):
            return correct_line(source, a.store, context_vocab={}, input_method='romaji',
                dict_index=a.dict_index, decisions=a.decisions, context_vec=a.context_vec)
        for source, expected in (('gakuseimohanashimasu', '学生も話します'),
                                 ('gakuseimohanashimasen', '学生も話しません'),
                                 ('shoruihatodokimasu', '書類は届きます')):
            with self.subTest(source=source):
                row = run(source)
                self.assertEqual(row['corrected'], expected)
                self.assertEqual(row['odd_spans'], [])
                self.assertEqual(row['analysis_status'], 'complete')
                self.assertEqual(row['diagnosis']['search_reports'], [])
        source = 'gakuseimohanashimasu'
        with patch.object(C, '_check_replacement', return_value=(None, 'forced_common_gate')):
            self.assertEqual(run(source)['corrected'], source)
        a.decisions.protect('seimoha')
        self.assertEqual(run(source)['corrected'], source)


if __name__ == '__main__':
    unittest.main()
