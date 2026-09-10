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
