"""Actual original-input ownership and cancellation for the mixed noun proof."""
import unittest
from unittest.mock import patch

import analysis_context as A
import corrector as C
from correction_entry import correct_line
import morphology as M
import reading_segments as R
from ime_session import _CURRENT
from last_choice import set_active
from tests_analysis_async import initial


@unittest.skipUnless(M.HAS_JANOME, 'actual bundled dictionary required')
class IndependentMixedNominalContracts(unittest.TestCase):
    def setUp(self):
        self.state = initial()
        self.addCleanup(set_active, None)

    def run_line(self, source):
        revision = self.state.store.revision()
        result = correct_line(source, self.state.store, input_method='kana',
            dict_index=self.state.dict_index, decisions=self.state.decisions, context_vec=None)
        self.assertEqual(self.state.store.revision(), revision)
        return result

    def assert_closed(self):
        self.assertIsNone(A._REQUEST_CHECK.get())
        self.assertIsNone(_CURRENT.get())
        self.assertEqual(C._CORRECTION_PATH.get(), ())

    def test_cancel_after_projected_actual_proof_accept_or_refusal_reaches_entry(self):
        revision = self.state.store.revision()
        original = R.native_object_predicate_proof
        for rejected in (False, True):
            source = ('スクりーン' if rejected else 'スくりーん') + 'をくたせさい。'
            with self.subTest(rejected=rejected):
                stale = [False]
                reached = []
                def checked(text, *args, **kwargs):
                    result = original(text, *args, **kwargs)
                    if text.startswith('スクリーンをください') and result:
                        reached.append((text, args, kwargs, result))
                        stale[0] = True
                        if rejected: result = False
                    return result
                original.cache_clear()
                with A.request_scope(lambda: stale[0], poll_interval=3600), \
                        patch.object(R, 'native_object_predicate_proof', side_effect=checked):
                    with self.assertRaises(A.SupersededAnalysis):
                        self.run_line(source)
                self.assertTrue(reached)
                self.assertEqual(self.state.store.revision(), revision)
                self.assert_closed()

    def test_cancel_after_actual_common_c_accept_or_refusal_reaches_entry(self):
        source = 'シャつをくたせさい。'
        revision = self.state.store.revision()
        original = C._check_replacement
        for rejected in (False, True):
            with self.subTest(rejected=rejected):
                stale = [False]
                reached = []
                def checked(line, edit, *args, **kwargs):
                    answer = original(line, edit, *args, **kwargs)
                    if line == source and edit[:3] == (4, 9, 'ください') and answer[0] is not None:
                        reached.append((line, edit, answer))
                        stale[0] = True
                        if rejected: answer = None, 'independent_C_refusal_at_cancel'
                    return answer
                with A.request_scope(lambda: stale[0], poll_interval=3600), \
                        patch.object(C, '_check_replacement', side_effect=checked):
                    with self.assertRaises(A.SupersededAnalysis):
                        self.run_line(source)
                self.assertTrue(reached)
                self.assertEqual(self.state.store.revision(), revision)
                self.assert_closed()


if __name__ == '__main__':
    unittest.main()
