# -*- coding: utf-8 -*-
"""An attested open source predicate is not a completed repair candidate."""
import copy
import unittest
from unittest.mock import patch

import corrector as C
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('する'), 'requires native dictionary')
class IncompleteCasePredicateTests(unittest.TestCase):
    def test_actual_nominative_and_continuative_own_the_source_end(self):
        for source in ('まちがし', '町がし', '水が流れ'):
            with self.subTest(source=source):
                self.assertTrue(R.native_incomplete_subject_predicate(source))
                self.assertEqual(R.native_incomplete_source_ranges(source), ((0, len(source)),))
                self.assertFalse(R.completed_native_reading_clause(source, require_object_fit=True))
                self.assertFalse(R.intact_native_reading(source, allow_incomplete=False))
        for source in ('ぷねらがし', '町がぷねら', '町がしる', '町がしぬ',
                       '町がしずか', '町がしを', '町ががし', 'はながさ',
                       '町がした', '本を読み', 'たべがし'):
            with self.subTest(not_open=source):
                self.assertFalse(R.native_incomplete_subject_predicate(source))

    def test_native_positions_readings_and_forms_cannot_be_invented(self):
        source='まちがし'
        original=M.tokenize(source)
        for part, field, value in ((-1, 'has_reading', False), (-1, 'reading', 'よみ'),
                (-1, 'base_form', '読む'), (-1, 'infl_form', '未然形'),
                (-1, 'pos', '名詞'), (-1, 'start', 2), (-1, 'end', 3),
                (-2, 'has_reading', False), (-2, 'pos_sub', '接続助詞'),
                (-2, 'reading', 'か'), (-2, 'end', 2), (0, 'start', 1)):
            parts=[copy.copy(t) for t in original]
            setattr(parts[part], field, value)
            with self.subTest(part=part, field=field, value=value), patch.object(M, 'tokenize', return_value=parts):
                self.assertFalse(R.native_incomplete_subject_predicate.__wrapped__(source))

    def test_quotation_column_and_sentence_do_not_lend_another_tail(self):
        for boundary in ('。', '！', '？', '.', '!', '?', '\t', '⇒'):
            source='まちがし'+boundary+'誤字'
            with self.subTest(boundary=boundary):
                self.assertEqual(R.native_incomplete_source_ranges(source), ((0, 4),))
                self.assertTrue(R.preserves_native_incomplete_source(source, source[:-2]+'文字'))
                self.assertFalse(R.preserves_native_incomplete_source(source, 'まぢかし'+source[4:]))
        source='「まちがし」と入力します。'
        self.assertEqual(R.native_incomplete_source_ranges(source), ((1, 5),))
        self.assertFalse(R.native_incomplete_source_ranges('まちがしぬ'))
        self.assertFalse(R.native_incomplete_source_ranges('まちがしずかです。'))

    def test_polite_probe_cannot_replace_the_original_host(self):
        source='まちがし';native_tokenize=M.tokenize
        for field,value in (('start', 2), ('base_form', '知る'), ('reading', 'よみ'),
                            ('infl_form', '未然形'), ('pos_sub', '非自立')):
            formed=[copy.copy(t) for t in native_tokenize(source+'ます')]
            host=next(t for t in formed if t.end==len(source))
            setattr(host, field, value)
            def tokens(text):
                return formed if text==source+'ます' else native_tokenize(text)
            with self.subTest(field=field), patch.object(M, 'tokenize', side_effect=tokens):
                self.assertFalse(R.native_incomplete_subject_predicate.__wrapped__(source))

    def test_shared_source_guard_stops_voicing_move_without_completing_candidate(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tokenize=C.make_tokenizer(a.store)
        try:
            for source, start in (('まちがし', 0), ('「まちがし」と入力します。', 1)):
                with self.subTest(source=source):
                    token=C._CORRECTION_SOURCE.set(source)
                    try:self.assertTrue(C._chunk_is_intact('まちがし', tokenize))
                    finally:C._CORRECTION_SOURCE.reset(token)
                    candidate, reason=C._check_replacement(source,
                        (start, start+4, 'まぢかし', 'かな入力'),
                        a.store, tokenize, a.dict_index, a.decisions)
                    self.assertIsNone(candidate)
                    self.assertEqual(reason, 'incomplete_original_source')
            # A source-only proof may not protect a prefix inside a different tail.
            self.assertFalse(R.native_incomplete_source_ranges('まちがしぬ'))
        finally:set_active(None)

    def test_initial_application_retains_open_prefix_and_regular_spelling(self):
        import app
        from janome_import import import_from_janome
        from tests_analysis_async import initial
        from last_choice import set_active
        for phase in ('seed', 'fresh'):
            a=initial()
            if phase=='fresh':import_from_janome(a.store)
            revision=a.store.revision()
            try:
                for source in ('まちがし', '町がし', 'まちがしずかです。',
                               'ほんをよみ', 'ひとがよみ'):
                    with self.subTest(phase=phase, source=source):
                        result=app.correct_line(source, a.store, input_method='kana',
                            dict_index=a.dict_index, decisions=a.decisions,
                            context_vec=a.context_vec if phase=='fresh' else None)
                        expected={'ほんをよみ':'本を読み', 'ひとがよみ':'人が読み'}.get(source, source)
                        self.assertEqual(result['corrected'], expected)
                        self.assertEqual(result.get('odd_spans'), [])
                        self.assertEqual(result.get('analysis_status'), 'complete')
                self.assertEqual(a.store.revision(), revision)
            finally:set_active(None)


if __name__=='__main__':unittest.main()
