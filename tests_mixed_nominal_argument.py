# -*- coding: utf-8 -*-
"""Whole mixed-script nouns keep their own meaning and source argument scope."""
import unittest
from unittest.mock import patch
import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'requires native Janome dictionary')
class MixedNominalArgumentTests(unittest.TestCase):
    def correct(self, source, method='kana', decisions=None):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a = initial()
        revision = a.store.revision()
        try:
            result = app.correct_line(source, a.store, dict_index=a.dict_index,
                decisions=decisions or a.decisions, context_vec=None, input_method=method)
            self.assertEqual(a.store.revision(), revision)
            self.assertEqual(result['analysis_status'], 'complete')
            return result
        finally:
            set_active(None)

    def test_request_keeps_the_literal_mixed_noun_and_passes_real_c(self):
        import corrector as C
        real_check = C._check_replacement
        accepted = []
        def check(line, edit, *args, **kwargs):
            result = real_check(line, edit, *args, **kwargs)
            if result[0] is not None:
                accepted.append((line, edit))
            return result
        for noun in ('スくりーん', 'スクりーン', 'シャつ'):
            source = noun + 'をくたせさい。'
            with self.subTest(source=source), patch.object(C, '_check_replacement', side_effect=check):
                result = self.correct(source)
                self.assertEqual(result['corrected'], noun + 'をください。')
                self.assertEqual(result['odd_spans'], [])
                self.assertIn(('くたせさい', 'ください', 'かな入力'), result['details'])
                self.assertTrue(any(line == source and edit[:3] == (len(noun)+1, len(noun)+6, 'ください')
                                    for line, edit in accepted))

    def test_whole_proof_cannot_borrow_another_face_case_or_field(self):
        import reading_segments as R
        self.assertTrue(R.native_object_predicate_proof('スくりーんをください。', 6, ('スクリーン',)))
        for text, cut, faces in (
                ('スくりーんをください。', 6, ('幕',)),
                ('スくりーんをください。', 6, ('スクリーン', '幕')),
                ('スくりーんをください。', 5, ('スクリーン',)),
                ('スくりーんのください。', 6, ('スクリーン',)),
                ('スくりーんを\tください。', 6, ('スクリーン',)),
                ('スくりーん甲をください。', 7, ('スクリーン',)),
                ('スくりーんを食べます。', 6, ('スクリーン',)),
                ('シャつを食べます。', 4, ('シャツ',)),
                ('ナりを食べます。', 3, ('成り',))):
            with self.subTest(text=text, cut=cut, faces=faces):
                self.assertFalse(R.native_object_predicate_proof(text, cut, faces))

    def test_c_rejection_and_partial_source_decisions_stop_the_new_scope(self):
        import corrector as C
        from decisions import DecisionStore
        source = 'スくりーんをくたせさい。'
        with patch.object(C, '_check_replacement', return_value=(None, 'fixture_shared_gate')) as gate:
            result = self.correct(source)
            self.assertTrue(gate.called)
            self.assertEqual(result['corrected'], source)
            self.assertEqual(result['odd_spans'], [(1, 11)])
        rejected = DecisionStore()
        self.assertTrue(rejected.reject('くたせさい', 'ください'))
        self.assertEqual(self.correct(source, decisions=rejected)['corrected'], source)
        protected = DecisionStore()
        self.assertTrue(protected.protect('くたせさい'))
        result = self.correct(source, decisions=protected)
        self.assertEqual(result['corrected'], source)
        self.assertEqual(result['odd_spans'], [])
        purple_only = DecisionStore()
        purple_only.leave_odd_alone('くたせさい')
        self.assertEqual(self.correct(source, decisions=purple_only)['corrected'], 'スくりーんをください。')

    def test_normal_opaque_classical_and_input_method_preserve_original_results(self):
        for source in ('スくりーんをください。', 'シャつをあらいます。',
                'コード値「キり」を使います。', '呼称は「ナり」です。',
                'スくりーん甲をくたせさい。', 'スくりーん_01をくたせさい。',
                '「スくりーん」をくたせさい。', 'ナりをくたせさい。'):
            with self.subTest(source=source):
                self.assertEqual(self.correct(source)['corrected'], source)
        source = 'スくりーんをくたせさい。'
        result = self.correct(source, method='romaji')
        self.assertEqual(result['corrected'], source)
        self.assertEqual(result['odd_spans'], [(1, 11)])

    def test_explicit_boundary_retains_the_existing_independent_request_scope(self):
        import contextual_repair as Q
        for separator in ('\t', '⇒', '。'):
            source = 'スくりーんを' + separator + 'くたせさい。'
            with self.subTest(separator=separator), patch.object(Q, 'resolve', wraps=Q.resolve) as resolve:
                result = self.correct(source)
                self.assertEqual(result['corrected'], 'スくりーんを' + separator + 'ください。')
                self.assertEqual(result['odd_spans'], [])
                targets = [call.args[0] for call in resolve.call_args_list]
                self.assertTrue(any(t.boundary_kind == 'kana_request' and t.start == 7 and t.end == 12
                                    for t in targets))
                self.assertFalse(any(t.boundary_kind == 'kana_predicate' for t in targets))


if __name__ == '__main__':
    unittest.main()
