# -*- coding: utf-8 -*-
"""CI failure reporting; ordinary runs still collect all mismatches."""
import os
from pathlib import Path
import sys
import unittest


class Checks:
    def __init__(self, failfast=False):
        self.failfast = failfast

    def _report(self, message, filename, line):
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            return
        escaped = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error file={filename},line={line}::{escaped}', flush=True)
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            try:
                with open(summary, 'a', encoding='utf-8') as out:
                    out.write('### 検査の不一致\n\n')
                    out.write('場所: ' + filename + ':' + str(line) + '\n\n')
                    out.write('\n'.join('    ' + s for s in message.splitlines()) + '\n\n')
                    if self.failfast:
                        out.write('最初の不一致で停止しました。残りは未実行で、全体合格ではありません。\n\n')
            except OSError as error:
                print(f'CI summary could not be written: {error}', file=sys.stderr)

    def failure(self, *parts):
        message = ' '.join(str(p) for p in parts)
        print(message, flush=True)
        caller = sys._getframe(1)
        self._report(message, Path(caller.f_code.co_filename).name, caller.f_lineno)
        if self.failfast:
            raise SystemExit(1)

    def run_suite(self, suite):
        result = unittest.TextTestRunner(verbosity=2, failfast=self.failfast).run(suite)
        if not result.wasSuccessful():
            caller = sys._getframe(1)
            details = [f'{test.id()}\n{trace}' for test, trace in result.failures + result.errors]
            details.extend('Unexpected success: ' + test.id() for test in result.unexpectedSuccesses)
            self._report('\n'.join(details), Path(caller.f_code.co_filename).name, caller.f_lineno)
            if self.failfast:
                raise SystemExit(1)
        return result
