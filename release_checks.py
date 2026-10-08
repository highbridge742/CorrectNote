# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Release gate for editor operations, startup and bundled resources on Windows.

Correction quality remains a separate, explicitly non-gating report. A successful
run of this script does not mean that ci_smoke_test.py passed.
"""
import sys
import unittest
from pathlib import Path


def main():
    if sys.platform != 'win32':
        raise SystemExit('Release checks require Windows; no GUI tests were run.')
    import morphology
    import public_nominal_cache
    from bundle_manifest import NAMES
    root = Path(__file__).resolve().parent
    assert morphology.HAS_JANOME, 'The bundled native dictionary is required'
    assert public_nominal_cache.available(), 'Public nominal cache is stale'
    for name in NAMES:
        assert (root/name).is_file(), ('Missing bundled resource', name)
    names = [
        'tests_ci_runner',
        'tests_exe_verification',
        'tests_toolbar_wordbook',
        'tests_word_book_native',
        'tests_editor_operations',
        'tests_bracket_composition',
        'tests_gui_startup',
        'tests_unicode_undo',
        'tests_gui_features',
        'tests_gui_shortcuts_menu',
        'tests_gui_editing.EditingTkTests',
        'tests_gui_editing.HalfwidthAutofixTkTests',
        'tests_gui_editing.CrossTabQuoteTests',
        'tests_gui_quote_continuation',
    ]
    # Subclasses add contracts but also inherit tests already selected above.
    import tests_gui_editing
    for case in (tests_gui_editing.QuickSentEnterTests, tests_gui_editing.QuoteEnterCommandTests):
        names.extend('tests_gui_editing.'+case.__name__+'.'+name for name in vars(case)
                     if name.startswith('test_'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    from ci_runner import Checks
    result = Checks().run_suite(suite)
    if not result.wasSuccessful():
        return 1
    print('RELEASE_OPERATIONS_OK: correction-quality suite is a separate report.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
