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
        'tests_long_literal_rows',
        'tests_text_unwrapped_gui',
        'tests_text_elided_gui',
        'tests_gui_quick_long',
        'tests_gui_encoded_paste',
        'tests_equal_text_positions',
        'tests_data_uri_literals',
        'tests_bulk_preview_positions',
        'tests_ruler_rows',
        'tests_ruler_rows_app',
        'tests_gui_link_native_states',
        'tests_wheel_glide',
        'tests_gui_literal_cancel',
        'tests_literal_lines',
        'tests_selection_clipboard',
        'tests_gui_ui_polish',
        'tests_toolbar_preferences',
        'tests_editor_guides',
        'tests_pending_rows',
        'tests_gui_pending_rows',
        'tests_text_links',
        'tests_text_links_gui',
        'tests_recent_files',
        'tests_undo_feedback',
        'tests_gui_undo_feedback',
        'tests_scroll_inertia',
        'tests_gui_wheel_options',
        'tests_quick_selection',
        'tests_gui_quick_selection',
        'tests_selection_native',
        'tests_selection_dispatch',
        'tests_quick_input_pause.QuickInputPauseTests',
        'tests_quick_idle_prewarm',
        'tests_gui_quick_idle',
        'tests_native_cancellation',
        'tests_request_polling',
        'tests_quick_row_reuse',
        'tests_gui_quick_rows',
        'tests_background_cancellation',
        'tests_headless_entry',
        'tests_gui_background_cancellation',
        'tests_ci_runner',
        'tests_exe_verification',
        'tests_toolbar_wordbook',
        'tests_word_book_native',
        'tests_bulk_insert',
        'tests_gui_bookmarks',
        'tests_gui_operation_followups',
        'tests_context_prepare',
        'tests_input_priority',
        'tests_startup_preparation',
        'tests_initial_worker_reuse',
        'tests_input_pending',
        'tests_input_pause',
        'tests_gui_input_pause',
        'tests_dictionary_reader',
        'tests_ime_poll_sharing',
        'tests_ime_language',
        'tests_ime_session',
        'tests_ime_lazy_search',
        'tests_worker_scopes',
        'tests_worker_prewarm',
        'tests_idle_prewarm',
        'tests_worker_reading_state',
        'tests_candidate_cache_state',
        'tests_quick_ime',
        'tests_gui_progress_quick',
        'tests_gui_footer_completion',
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
