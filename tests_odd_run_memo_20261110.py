"""correction_entry: 1行の中で corrector._convert_odd_kana_run の同じ呼び出しを使い回す（答えは変えない）。"""
import unittest
from unittest import mock

import correction_entry as CE
import corrector


class OddRunMemoTests(unittest.TestCase):
    def test_installed(self):
        self.assertEqual(corrector._convert_odd_kana_run.__qualname__, '_convert_odd_kana_run_memo')

    def test_memo_only_inside_line(self):
        calls = []

        def raw(text, store, di, **k):
            calls.append(text)
            return None
        with mock.patch.object(CE, '_ODD_RUN_RAW', raw):
            CE._convert_odd_kana_run_memo('あ', 1, 2)
            CE._convert_odd_kana_run_memo('あ', 1, 2)
            self.assertEqual(len(calls), 2)
            tok = CE._ODD_RUN_MEMO.set({})
            try:
                CE._convert_odd_kana_run_memo('あ', 1, 2, strict_anchor=True)
                CE._convert_odd_kana_run_memo('あ', 1, 2, strict_anchor=True)
                CE._convert_odd_kana_run_memo('あ', 1, 2)
            finally:
                CE._ODD_RUN_MEMO.reset(tok)
            self.assertEqual(len(calls), 4)


class LexicalOmissionMemoTests(unittest.TestCase):
    def test_memo_inside_line(self):
        calls = []

        def raw(*a, **k):
            calls.append(a[0])
            return ()
        with mock.patch.object(CE, '_LOR_RAW', raw):
            tok = CE._ODD_RUN_MEMO.set({})
            try:
                CE._lexical_omission_memo('かくにん', None)
                CE._lexical_omission_memo('かくにん', None)
            finally:
                CE._ODD_RUN_MEMO.reset(tok)
            CE._lexical_omission_memo('かくにん', None)
        self.assertEqual(len(calls), 2)


class ReopenVariantCapTests(unittest.TestCase):
    def test_cap_inside_reopen_only(self):
        import os
        calls = []

        def raw(text, store, di, **k):
            calls.append(text)
            return None

        def reopen(*a, **k):
            for i in range(5):
                corrector._convert_odd_kana_run('か%d' % i, 1, 2, short_head=True, born=None)
            return None
        with mock.patch.object(CE, '_ODD_RUN_RAW', raw), mock.patch.object(CE, '_REOPEN_RAW', reopen), \
                mock.patch.dict(os.environ, {'CN_REOPEN_VARIANT_CAP': '3'}):
            CE._reopen_odd_chunk_capped('かかか')
            self.assertEqual(len(calls), 3)
            CE._convert_odd_kana_run_memo('か9', 1, 2, short_head=True, born=None)
            self.assertEqual(len(calls), 4)


if __name__ == '__main__':
    unittest.main()
