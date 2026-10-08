# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the release verifier with synthetic archive entries, never user data."""
import contextlib
import io
import marshal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_built_exe as V
from bundle_manifest import NAMES


class ExeVerificationTests(unittest.TestCase):
    def verify(self, extra=(), missing=()):
        root = Path(V.__file__).resolve().parent
        modules = {'analysis_cache', 'contextual_repair', 'ime_colloquial',
                   'seed_japanese', 'word_book', 'menu_hover'} - set(missing)
        def code(name):
            return compile((root / (name + '.py')).read_text(encoding='utf8'),
                           name + '.py', 'exec')
        class Pyz:
            toc = dict.fromkeys(modules)
            def extract(self, name): return code(name)
        class Archive:
            toc = dict.fromkeys(['app', 'PYZ.pyz'] + list(NAMES) + list(extra))
            def open_embedded_archive(self, name):
                assert name == 'PYZ.pyz'
                return Pyz()
            def extract(self, name):
                if name == 'app': return marshal.dumps(code('app'))
                return (root / name).read_bytes()
        with tempfile.TemporaryDirectory(prefix='correctnote-exe-verifier-') as tmp:
            exe = Path(tmp) / 'synthetic.exe'; exe.write_bytes(b'synthetic')
            with patch.object(V, 'CArchiveReader', return_value=Archive()), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                V.main(exe)
            return output.getvalue()

    def test_public_source_and_assets_are_accepted(self):
        self.assertIn('EXE_VERIFIED APP_VERSION=', self.verify())

    def test_word_book_data_and_atomic_temporary_file_are_rejected(self):
        for name in ('word_book.json', 'word_book.json.tmp',
                     'nested/word_book.json', r'nested\word_book.json.tmp'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(AssertionError, 'personal data included'):
                    self.verify(extra=(name,))

    def test_windows_case_does_not_hide_private_data(self):
        for name in ('WORD_BOOK.JSON', r'private\SESSION.JSON'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(AssertionError, 'personal data included'):
                    self.verify(extra=(name,))

    def test_new_ui_modules_cannot_be_silently_omitted(self):
        for name in ('word_book', 'menu_hover'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(AssertionError, 'module missing from EXE'):
                    self.verify(missing=(name,))


if __name__ == '__main__':
    unittest.main()
