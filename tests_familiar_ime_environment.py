# -*- coding: utf-8 -*-
"""Live source IME proof complements the native-only lattice regressions."""
import unittest
from unittest.mock import patch
from morphology import HAS_JANOME


@unittest.skipUnless(HAS_JANOME,'Requires real Janome')
class FamiliarLiveIMEEnvironmentTests(unittest.TestCase):
    def test_exact_live_context_finishes_native_bound_stem_source(self):
        import app, contextual_repair as Q, corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        from ime_inverse_gate import exact_context_reading
        from ime_language import JapaneseIME
        source='説明を纏路手資料にしました。'
        state=initial()
        try:
            with JapaneseIME() as ime:
                if not ime.available:self.skipTest('Requires native IFELanguage')
            tok=C.make_tokenizer(state.store)
            target=next(t for t in Q.targets_for_line(source,tok,state.store,state.dict_index)
                        if t.text=='纏路手資料')
            exact=exact_context_reading(target.context,target.start-target.context_start,
                                        target.end-target.context_start)
            if not exact or exact[0]!='まとろてしりょう':
                self.skipTest('Installed IME has no exact source-context proof for this branch')
            def run(text):
                current=initial()
                return app.correct_line(text,current.store,input_method='kana',dict_index=current.dict_index,
                                        decisions=current.decisions,context_vec=None)
            with patch.object(C,'_check_replacement',wraps=C._check_replacement) as gate:
                result=run(source)
            self.assertGreater(gate.call_count,0)
            self.assertEqual(result['corrected'],'説明をまとめて資料にしました。')
            self.assertEqual(result['odd_spans'],[])
            self.assertEqual(result['analysis_status'],'complete')
            self.assertFalse(any(row.get('state')=='truncated' for row in result.get('search_reports',())))
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')) as gate:
                result=run(source)
            self.assertGreater(gate.call_count,0)
            self.assertEqual(result['corrected'],source)
            self.assertTrue(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            for normal in ('説明をまとめて資料にしました。','道路の資料を読みます。',
                           '「説明を纏路手資料にしました」という文字列です。'):
                with self.subTest(source=normal):
                    result=run(normal)
                    self.assertEqual(result['corrected'],normal)
                    self.assertEqual(result['odd_spans'],[])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)


if __name__=='__main__':unittest.main()
