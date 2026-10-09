# -*- coding: utf-8 -*-
"""Native quantity owners share readings without bypassing their context proof."""
import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,semantic_owner_spelling as W


class _Search:
    available=False
    faces=()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def candidates(self,reading):return self.faces


@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class CounterOwnerSpellingTests(unittest.TestCase):
    def test_native_quantity_supply_preserves_same_reading_and_counter(self):
        W._owner_readings('の')
        for available in (False,True):
            search=_Search();search.available=available
            search.faces=('荷台','三台','二台','二台','二代','にだい')
            with self.subTest(available=available),patch('ime_candidates.SearchCandidates',return_value=search):
                self.assertEqual(W._owners('にだい','の'),('二台',))
                # Same counter is insufficient: the number's reading also matters.
                self.assertEqual(R.native_counted_nominal_evidence('三台'),R.native_counted_nominal_evidence('にだい'))
                self.assertFalse(M.native_spelling_only('にだい','三台'))
                self.assertFalse(R.native_counted_nominal_evidence('荷台'))
        with patch('ime_candidates.SearchCandidates',return_value=_Search()):
            for raw,face in (('さんだい','三台'),('いちまい','一枚'),('にまい','二枚')):
                with self.subTest(raw=raw):self.assertIn(face,W._owners(raw,'の'))

    def test_native_reading_and_existing_proof_are_both_required(self):
        W._owner_readings('の')
        with patch('ime_candidates.SearchCandidates',return_value=_Search()):
            with patch('reading_segments.native_counter_readings',return_value={}):
                self.assertEqual(W._owners('にだい','の'),())
            with patch('reading_segments.native_counted_nominal_evidence',return_value=None):
                self.assertEqual(W._owners('にだい','の'),())
            with patch('morphology.native_spelling_only',return_value=False):
                self.assertEqual(W._owners('にだい','の'),())
            self.assertEqual(W._owners('にだい','に'),())

    def test_owner_relation_and_original_scope_are_still_required(self):
        import context_meaning as K
        source='仕事でにだいのきかいをつかう'
        with patch('ime_candidates.SearchCandidates',return_value=_Search()):
            frames=W.frames(source)
            self.assertEqual([(f['start'],f['end'],f['surface'],f['owner_spelling']['prefix']) for f in frames],
                             [(3,10,'にだいのきかい','二台の')])
            for f in frames:
                self.assertEqual(f['evidence_start'],3)
                self.assertEqual(K.candidates(f),('二台の機械',))
            with patch.object(W,'_owner_boundary',return_value=False):self.assertFalse(W.frames(source))
            with patch.object(K,'candidates',return_value=[]):self.assertFalse(W.frames(source))
            for other in ('にだい','にだいのにもつをおく','荷台の機械を使う',
                          'にだい\tきかいをつかう','「にだいのきかいをつかう」という文字列'):
                with self.subTest(source=other):self.assertFalse(W.frames(other))

    def _correct(self,source):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        from ime_inverse_gate import _CORRECTION_CACHE
        state=initial();revision=state.store.revision();token=_CORRECTION_CACHE.set({})
        try:
            result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                                    decisions=state.decisions,context_vec=None)
            self.assertEqual(state.store.revision(),revision)
            self.assertEqual(result['analysis_status'],'complete')
            return result
        finally:_CORRECTION_CACHE.reset(token);set_active(None)

    def test_initial_runtime_uses_source_quantity_without_os_proposals(self):
        with patch('ime_candidates.SearchCandidates',return_value=_Search()):
            for source,expected in (('にだいのきかいをつかう','二台の機械を使う'),
                                    ('さんだいのきかいをつかう','三台の機械を使う'),
                                    ('荷台の機械を使う','荷台の機械を使う'),
                                    ('にだい','にだい'),
                                    ('「にだいのきかいをつかう」という文字列','「にだいのきかいをつかう」という文字列')):
                with self.subTest(source=source):
                    result=self._correct(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])

    def test_quantity_candidate_reaches_common_final_gate(self):
        import corrector as C
        source='仕事でにだいのきかいをつかう'
        with patch('ime_candidates.SearchCandidates',return_value=_Search()):
            with patch.object(C,'_check_replacement',wraps=C._check_replacement) as gate:
                result=self._correct(source)
            self.assertEqual(result['corrected'],'仕事で二台の機械を使う')
            self.assertTrue(any(call.args[0]==source and call.args[1][:3]==(3,10,'二台の機械')
                                for call in gate.call_args_list))
            with patch.object(C,'_check_replacement',return_value=(None,'counter_gate_fixture')) as gate:
                rejected=self._correct(source)
            self.assertTrue(any(call.args[0]==source and call.args[1][:3]==(3,10,'二台の機械')
                                for call in gate.call_args_list))
            self.assertEqual(rejected['corrected'],source)


if __name__=='__main__':unittest.main()
