# -*- coding: utf-8 -*-
"""The CI harness must fail promptly without weakening the underlying checks."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ci_runner import Checks


class CIRunnerTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stderr = contextlib.redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def test_direct_mismatch_stops_with_its_diagnostic(self):
        with self.assertRaises(SystemExit) as stopped:
            Checks(failfast=True).failure('[NG] input', 'actual', 'expected')
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn('[NG] input actual expected', self.output.getvalue())

    def test_diagnostic_mode_keeps_collecting(self):
        events = []
        class Sample(unittest.TestCase):
            def test_a(self):
                self.fail('first mismatch')
            def test_b(self):
                events.append('second test')
                self.fail('second mismatch')
        checks = Checks()
        checks.failure('[NG] direct mismatch')
        result = checks.run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Sample))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.failures), 2)
        self.assertEqual(events, ['second test'])

    def test_failure_error_and_subtest_stop_after_cleanup(self):
        for kind in ('failure', 'error', 'subtest'):
            events = []
            class Sample(unittest.TestCase):
                @classmethod
                def tearDownClass(cls):
                    events.append('class cleanup')
                def test_a(self):
                    self.addCleanup(events.append, 'cleanup')
                    if kind == 'error':
                        raise RuntimeError('fixture error')
                    if kind == 'subtest':
                        with self.subTest(part=1):
                            self.fail('subtest mismatch')
                        events.append('after subtest')
                    else:
                        self.fail('mismatch')
                def test_b(self):
                    events.append('must not execute')
            with self.subTest(kind=kind), self.assertRaises(SystemExit) as stopped:
                Checks(failfast=True).run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Sample))
            self.assertEqual(stopped.exception.code, 1)
            self.assertEqual(events, ['cleanup', 'class cleanup'])

    def test_success_runs_every_test(self):
        events = []
        class Sample(unittest.TestCase):
            def test_a(self):
                events.append('a')
            def test_b(self):
                events.append('b')
        result = Checks(failfast=True).run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Sample))
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(events, ['a', 'b'])

    def test_unexpected_success_is_still_failure(self):
        class Sample(unittest.TestCase):
            @unittest.expectedFailure
            def test_a(self):
                pass
        with self.assertRaises(SystemExit) as stopped:
            Checks(failfast=True).run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Sample))
        self.assertEqual(stopped.exception.code, 1)

    def test_actions_summary_keeps_failure_details_and_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.md'
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_STEP_SUMMARY': str(summary)}):
                with self.assertRaises(SystemExit):
                    Checks(failfast=True).failure('input 50%\nactual\rexpected')
            self.assertIn('50%25%0Aactual%0Dexpected', self.output.getvalue())
            content = summary.read_text(encoding='utf8')
            self.assertIn('tests_ci_runner.py:', content)
            self.assertIn('input 50%', content)
            self.assertIn('残りは未実行', content)

    def test_suite_summary_names_failed_test_and_expectation(self):
        class Sample(unittest.TestCase):
            def test_expected_value(self):
                self.assertEqual('actual', 'expected')
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.md'
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_STEP_SUMMARY': str(summary)}):
                with self.assertRaises(SystemExit):
                    Checks(failfast=True).run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Sample))
            content = summary.read_text(encoding='utf8')
            self.assertIn('test_expected_value', content)
            self.assertIn('actual', content)
            self.assertIn('expected', content)

    def test_summary_write_error_does_not_replace_failure_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_STEP_SUMMARY': directory}):
                with self.assertRaises(SystemExit) as stopped:
                    Checks(failfast=True).failure('mismatch')
            self.assertEqual(stopped.exception.code, 1)
            self.assertIn('could not be written', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
