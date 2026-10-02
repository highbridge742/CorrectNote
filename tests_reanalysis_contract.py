# -*- coding: utf-8 -*-
"""再解析の終了条件。本文と呼出し状態を実際に検査する。"""
import unittest
import corrector as C


class ReanalysisContractTests(unittest.TestCase):
    def test_nonrepeating_chain_is_bounded_and_restores_source(self):
        calls = []
        @C._with_correction_source
        def run(text):
            calls.append(text)
            return run(text + 'あ')
        result = run('原文')
        self.assertEqual(len(calls), C.MAX_CORRECTION_DEPTH)
        self.assertEqual(result['corrected'], '原文')
        self.assertFalse(result['changed'])
        self.assertEqual(result['stop_reason'], 'depth_limit')
        self.assertEqual(result['unsure_spans'], [(0, 2)])
        self.assertNotIn('diagnostic_cycle', result)
        self.assertIsNone(C._CORRECTION_SOURCE.get())
        self.assertEqual(C._CORRECTION_PATH.get(), ())

    def test_cycle_is_distinct_from_budget(self):
        @C._with_correction_source
        def run(text):
            return run('乙' if text == '甲' else '甲')
        result = run('甲')
        self.assertEqual(result['corrected'], '甲')
        self.assertEqual(result['stop_reason'], 'cycle')
        self.assertTrue(result['diagnostic_cycle'])
        self.assertNotIn('diagnostic_limit', result)

    def test_success_after_failure_has_fresh_context(self):
        @C._with_correction_source
        def run(text, remaining):
            if remaining:
                return run(text + 'い', remaining - 1)
            return {'corrected': text, 'source': C._CORRECTION_SOURCE.get()}
        run('失敗', C.MAX_CORRECTION_DEPTH + 1)
        result = run('次', 2)
        self.assertEqual(result, {'corrected': '次いい', 'source': '次'})

    def test_exception_does_not_leak_context(self):
        @C._with_correction_source
        def run(text):
            raise ValueError('failure')
        with self.assertRaises(ValueError):
            run('原文')
        self.assertIsNone(C._CORRECTION_SOURCE.get())
        self.assertEqual(C._CORRECTION_PATH.get(), ())

    def test_last_allowed_level_completes(self):
        @C._with_correction_source
        def run(text):
            if len(text) < C.MAX_CORRECTION_DEPTH:
                return run(text + 'あ')
            return text
        self.assertEqual(len(run('あ')), C.MAX_CORRECTION_DEPTH)


if __name__ == '__main__':
    unittest.main()


class ReanalysisDisplayTests(unittest.TestCase):
    def test_checked_word_keeps_nonempty_transposition_pair(self):
        source='前abc後';changed='前acb後'
        self.assertEqual(C._display_spans_for_reanalysis(source,changed,[(1,4,'acb','かな入力')]),[(1,4,1,4)])

    def test_inner_change_and_unproved_scope_do_not_borrow_display_proof(self):
        source='前abc後'
        self.assertEqual(C._display_spans_for_reanalysis(source,'前acb後',[]),list(C._diff_spans(source,'前acb後')))
        self.assertEqual(C._display_spans_for_reanalysis(source,'前acd後',[(1,4,'acb','かな入力')]),list(C._diff_spans(source,'前acd後')))

    def test_prior_length_change_maps_same_checked_word(self):
        source='AAabcZ';changed='BacbZ'
        rows=C._display_spans_for_reanalysis(source,changed,[(0,2,'B','表記補正'),(2,5,'acb','かな入力')])
        self.assertIn((2,5,1,4),rows)
        self.assertEqual(''.join(changed[c:d] if a!=b else changed[c:d] for a,b,c,d in rows),'Bacb')

    def test_written_source_feedback_keeps_actual_candidate_word(self):
        import app,units
        from tests_analysis_async import initial
        from decisions import DecisionStore
        for source in ('資料を保存したない','「資料」という語。資料を保存したない'):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertTrue(r['corrected'].endswith('保存したいな'))
                self.assertIn(('保存したない','保存したいな','かな入力'),[tuple(x) for x in r['details']])
                _,shown=units.build_line_units(r,C.make_tokenizer(a.store))
                self.assertTrue(any(u.get('detail') and u['detail'][0]=='保存したない' for u in shown))
                d=DecisionStore();d.reject('保存したない','保存したいな')
                held=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=d,context_vec=None)
                self.assertEqual(held['corrected'],source)
