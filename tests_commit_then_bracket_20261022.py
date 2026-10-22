# -*- coding: utf-8 -*-
"""The bracket key right after an IME commit wraps what was just committed (2026-10-22).

うにさん「漢字変換中の F2は、何も起きませんでした」: while candidates are shown the IME keeps
F2. Chosen remedy (A): press Enter to commit, then F2 wraps the text just committed, and
pressing again changes the pair. The committed characters are the ones Tk delivers as the
IME's (%E = -3); here that delivery is replayed in Tk's order (our tag first, then the Text
class inserts the character). Nothing about keys is stored. Withdrawn root."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, ime_watch
import tests_bracket_composition as bracket_tests


class CommitThenBracketTests(unittest.TestCase):
    setUp = bracket_tests.BracketCompositionTests.setUp
    tearDown = bracket_tests.BracketCompositionTests.tearDown

    def ready(self, w, text='前後', cursor='1.1'):
        self.a._install_commit_run(w)
        w.delete('1.0', 'end'); w.insert('1.0', text); w.mark_set('insert', cursor)
        self.a._forget_bracket_cycle(); self.a._forget_commit_run()

    def commit(self, w, text, marker='1'):
        # One IME result: Tk delivers its characters as key events (%E is 1 for every key in
        # Tk 8.6.12, -3 for IME characters in Tk 8.6.9), and the IME reports the result string.
        for ch in text:
            self.a._on_commit_run_event('key', marker, '??', str(w))
            w.insert('insert', ch)
        self.a._note_ime_result(w, text)
        self.root.update()

    def key(self, w, keysym):
        self.a._on_commit_run_event('key', '0', keysym, str(w))

    def bracket(self, w, state=0):
        self.key(w, 'F2')
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._on_f5_brackets(SimpleNamespace(widget=w, keysym='F2', char='', state=state))

    def test_bracket_key_wraps_the_commit_and_cycles(self):
        w = self.editor; self.ready(w)
        self.commit(w, '漢字')
        self.bracket(w)
        self.assertEqual(w.get('1.0', 'end-1c'), '前（漢字）後')
        self.bracket(w)
        self.assertEqual(w.get('1.0', 'end-1c'), '前「漢字」後')
        self.assertTrue(self.a._cancel_bracket_cycle())
        self.assertEqual(w.get('1.0', 'end-1c'), '前漢字後')

    def test_modifiers_choose_the_pair(self):
        w = self.editor
        for state, expected in ((1, '前『漢字』後'), (4, '前（漢字）後'), (5, '前“漢字”後'),
                                (0x20000, '前漢字（）後')):             # Alt+F2: a pair at the cursor
            with self.subTest(state=state):
                self.ready(w); self.commit(w, '漢字'); self.bracket(w, state)
                self.assertEqual(w.get('1.0', 'end-1c'), expected)

    def test_only_the_last_commit(self):
        w = self.editor; self.ready(w)
        self.commit(w, '一つ目')
        self.commit(w, '二つ目')
        self.bracket(w)
        self.assertEqual(w.get('1.0', 'end-1c'), '前一つ目（二つ目）後')

    def test_anything_in_between_leaves_an_empty_pair_at_the_cursor(self):
        w = self.editor
        for between in ('Left', 'a', 'click', 'focus', 'moved', 'edited'):
            with self.subTest(between=between):
                self.ready(w); self.commit(w, '漢字')
                if between == 'click':self.a._on_commit_run_event('button', '0', '', str(w))
                elif between == 'focus':self.a._on_commit_run_event('focus', '0', '', str(w))
                elif between == 'moved':w.mark_set('insert', '1.0')
                elif between == 'edited':w.insert('1.1', '変')       # e.g. a correction rewrote it
                else:self.key(w, between)
                before = w.get('1.0', 'end-1c'); cursor = w.index('insert')
                self.bracket(w)
                self.assertNotIn('（漢字）', w.get('1.0', 'end-1c'))
                self.assertEqual(w.get('1.0', 'end-1c'), before[:len(w.get('1.0', cursor))] + '（）'
                                 + before[len(w.get('1.0', cursor)):])

    def test_ctrl_wraps_the_last_conversion_even_after_moving(self):
        # 2026-10-22 うにさん「Ctrl+F2を　直前の変換に対して括弧で括る」: the last commit, while its
        # text is still as it was, even after the cursor moved or other keys were pressed.
        w = self.editor; self.ready(w, '前後', '1.1')
        self.commit(w, '漢字')
        w.mark_set('insert', '1.0'); self.key(w, 'Left'); self.a._on_commit_run_event('button', '0', '', str(w))
        self.bracket(w, 4)
        self.assertEqual(w.get('1.0', 'end-1c'), '前（漢字）後')
        self.bracket(w, 4)
        self.assertEqual(w.get('1.0', 'end-1c'), '前「漢字」後')
        self.assertTrue(self.a._cancel_bracket_cycle())
        self.assertEqual(w.get('1.0', 'end-1c'), '前漢字後')

    def test_ctrl_without_a_conversion_left_works_as_before(self):
        w = self.editor; self.ready(w, '前後', '1.1')
        self.commit(w, '漢字'); w.insert('1.2', '変')        # the conversion was edited since
        self.bracket(w, 4)
        self.assertNotIn('（漢字）', w.get('1.0', 'end-1c'))

    def test_alt_ignores_selection_and_commit(self):
        w = self.editor; self.ready(w, '選ぶ前後', '1.3')
        self.commit(w, '漢字'); w.tag_add('sel', '1.0', '1.2')
        self.bracket(w, 0x20000)
        self.assertEqual(w.get('1.0', 'end-1c'), '選ぶ前漢字（）後')

    def test_a_selection_still_wins(self):
        w = self.editor; self.ready(w, '選ぶ前後', '1.3')
        self.commit(w, '漢字')
        w.tag_add('sel', '1.0', '1.2')
        self.bracket(w)
        self.assertEqual(w.get('1.0', 'end-1c'), '（選ぶ）前漢字後')

    def test_another_tab_does_not_wrap(self):
        w = self.editor; self.ready(w)
        self.commit(w, '漢字'); self.tab = {}
        self.bracket(w)
        self.assertNotIn('（漢字）', w.get('1.0', 'end-1c'))

    def test_quick_input_too(self):
        q = tk.Text(self.root); q.pack(); self.a._quick_text = q
        self.a._on_quick_change = lambda *args: None      # quick analysis is not part of this
        self.ready(q, '前後'); self.commit(q, '漢字')
        self.bracket(q)
        self.assertEqual(q.get('1.0', 'end-1c'), '前（漢字）後')
        self.assertEqual(self.editor.get('1.0', 'end-1c'), '前後')

    def test_the_ime_result_decides_in_both_tk_versions(self):
        # Tk 8.6.12 (the release build) gives every key event %E=1, typed or not (2026-10-22
        # うにさん「開発版は付く」が、配布版では付かなかった). The IME's own result string decides.
        w = self.editor
        for marker in ('-3', '1'):
            with self.subTest(marker=marker):
                self.ready(w); self.commit(w, '漢字', marker); self.bracket(w)
                self.assertEqual(w.get('1.0', 'end-1c'), '前（漢字）後')
        self.ready(w)
        for ch in 'ab':                                   # typed: %E=1 too, but no IME result
            self.a._on_commit_run_event('key', '1', ch, str(w)); w.insert('insert', ch)
        self.root.update(); self.bracket(w)
        self.assertEqual(w.get('1.0', 'end-1c'), '前ab（）後')

    def test_result_reported_before_tk_inserts_it_waits(self):
        w = self.editor; self.ready(w)
        self.a._note_ime_result(w, '漢字')                  # not inserted yet
        self.assertIsNone(self.a._last_conversion_range(w))
        w.insert('insert', '漢字')
        self.bracket(w)
        self.assertEqual(w.get('1.0', 'end-1c'), '前（漢字）後')

    def test_window_procedure_commits_go_to_their_text_box(self):
        # Tk keeps the Windows focus on the top-level window, so the IME's result arrives in the
        # window procedure (_on_message), which queues (hwnd, text); the IME timer hands it over.
        q = tk.Text(self.root); q.pack(); self.a._quick_text = q
        self.a._on_quick_change = lambda *args: None
        self.a._quick_drop_hwnds = [111, 112]
        self.ready(self.editor); self.ready(q)
        self.editor.insert('insert', '漢字'); q.insert('insert', '簡易')
        self.a._ime_commit_queue = [(100, '漢字'), (112, '簡易')]
        self.a._take_ime_commits()
        self.assertEqual(self.a._ime_commit_queue, [])
        self.assertEqual(self.a._last_conversion_range(q), ('1.0+1c', '1.0+3c'))   # the later one
        self.bracket(q)
        self.assertEqual(q.get('1.0', 'end-1c'), '前（簡易）後')

    def test_tag_is_first_and_installed_once(self):
        w = self.editor
        for _ in range(3):self.a._install_commit_run(w)
        self.assertEqual(w.bindtags()[0], app.CorrectNoteApp.COMMIT_RUN_TAG)
        self.assertEqual(w.bindtags().count(app.CorrectNoteApp.COMMIT_RUN_TAG), 1)


if __name__ == '__main__':
    unittest.main()
