# -*- coding: utf-8 -*-
"""Existing counted-object meanings reach native phrase and final checks."""
import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('枚'),'requires native dictionary')
class CountedSharedRoleTests(unittest.TestCase):
    def test_existing_context_roles_share_exact_native_quantity_only(self):
        for source in ('一枚','いちまい','二枚','2枚','２枚','100枚','一枚半'):
            with self.subTest(source=source):
                self.assertEqual(S.counted_genitive_roles(source),frozenset(('sheet_object',)))
                self.assertIsNone(S.counted_object_roles(source))
                self.assertNotIn('sheet_object',S.nominal_roles(source))
        for source in ('一枚目','いちまいめ','2枚目','一個','一つ','枚','1X枚','知らない枚'):
            with self.subTest(source=source):self.assertIsNone(S.counted_genitive_roles(source))
        self.assertEqual(S.counted_object_roles('二台'),frozenset(('device',)))
        self.assertEqual(S.counted_object_roles('二冊'),frozenset(('text','reference')))
        self.assertEqual(S.counted_object_roles('二人'),frozenset(('person',)))
        self.assertEqual(S.counted_genitive_roles('二台'),frozenset(('device',)))
        for source in ('一枚目','二枚目','いちまいめ'):
            self.assertIsNone(S.counted_object_roles(source))
            self.assertIsNone(S.counted_genitive_roles(source))
            self.assertNotIn('sheet_object',S.nominal_roles(source))

    def test_same_written_head_and_original_case_prove_the_phrase(self):
        for source,head,verb in (('一枚の紙','紙','折る'),('一枚の布','布','切る'),
                                 ('二枚の皿','皿','洗う')):
            with self.subTest(source=source):
                self.assertEqual(R.native_surface_nominal_heads(source),(head,))
                self.assertTrue(R.native_object_predicate_proof(source+'を'+verb,len(source)+1,(head,)))
        self.assertFalse(R.native_surface_nominal_heads('一枚の機械'))
        self.assertFalse(R.native_surface_nominal_heads('一枚の飲料'))
        self.assertFalse(R.native_surface_nominal_heads('一枚\tの紙'))
        self.assertFalse(R.native_object_predicate_proof('一枚の紙を飲む',5,('紙',)))
        # The shared meaning does not supply a missing quantity or noun proof.
        with patch.object(R,'native_counted_nominal_evidence',return_value=()):
            self.assertIsNone(S.counted_genitive_roles('一枚'))

    def _run(self,source):
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

    def test_runtime_completes_the_same_quantity_after_partial_spelling(self):
        for source,wanted in (('いちまいのかみをおる','一枚の紙を折る'),
                              ('いちまいの紙を折る','一枚の紙を折る'),
                              ('にまいのかみをおる','二枚の紙を折る')):
            with self.subTest(source=source):
                result=self._run(source)
                self.assertEqual(result['corrected'],wanted)
                self.assertEqual(result['odd_spans'],[])
        for source in ('一枚の紙を折る','一枚の布を切る','一枚の皿を洗う',
                       'いちまい','「いちまいのかみをおる」という文字列'):
            with self.subTest(source=source):
                result=self._run(source)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['odd_spans'],[])

    def test_shared_quantity_still_reaches_the_original_common_gate(self):
        import corrector as C
        source='いちまいの紙を折る'
        with patch.object(C,'_check_replacement',wraps=C._check_replacement) as gate:
            result=self._run(source)
        self.assertEqual(result['corrected'],'一枚の紙を折る')
        self.assertTrue(any(c.args[0]==source and c.args[1][:3]==(0,6,'一枚の紙')
                            for c in gate.call_args_list))
        with patch.object(C,'_check_replacement',return_value=(None,'shared_quantity_gate')) as gate:
            result=self._run(source)
        self.assertTrue(any(c.args[0]==source and c.args[1][:3]==(0,6,'一枚の紙')
                            for c in gate.call_args_list))
        self.assertEqual(result['corrected'],source)


if __name__=='__main__':unittest.main()
