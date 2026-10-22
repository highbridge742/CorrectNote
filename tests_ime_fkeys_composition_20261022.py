# -*- coding: utf-8 -*-
"""F1/F2 pressed while the IME is converting act on the committed text (2026-10-22).

うにさん: 「入力中にF2すると、入力中の1文字目だけが、上の行の文字の末尾に入ります」、
F1 は確定後に「打った文字の左に」引用した。The key arrived before the converted text
existed in the widget, so the cursor (a line start here) and the target were taken from
the text before it. Now the conversion is committed first, as F5 does, and the key runs
again with the cursor after the committed text. Withdrawn root; no clipboard."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk
import app, ime_watch
import tests_bracket_composition as bracket_tests

COMP = '変換中'


class FunctionKeysDuringConversionTests(unittest.TestCase):
    setUp = bracket_tests.BracketCompositionTests.setUp
    tearDown = bracket_tests.BracketCompositionTests.tearDown
    wait = bracket_tests.BracketCompositionTests.wait

    def line_start(self):
        # Typing at the start of the second row: the case that put a character
        # at the end of the row above.
        self.editor.delete('1.0', 'end');self.editor.insert('1.0', '上の行\n')
        self.editor.mark_set('insert', '2.0');self.a._forget_bracket_cycle()
        self.active = [True]
        def commit(hwnd):
            def native():self.editor.insert('insert', COMP);self.active[0] = False
            self.root.after(30, native);return True
        return (patch.object(ime_watch, 'composition_active', side_effect=lambda hwnd:self.active[0]),
                patch.object(ime_watch, 'read_composition', return_value={'comp':COMP}),
                patch.object(ime_watch, 'complete_composition', side_effect=commit))

    def key(self, keysym):
        return SimpleNamespace(widget=self.editor, keysym=keysym, char='', state=0, keycode=0)

    def test_action_waits_for_the_commit_and_sees_the_cursor_after_it(self):
        seen = []
        a, b, c = self.line_start()
        with a, b, c:
            took = self.a._commit_composition_first(self.key('F2'),
                lambda event:seen.append((event.widget, self.editor.index('insert'), self.editor.get('1.0', 'end-1c'))))
            self.assertTrue(took);self.assertEqual(seen, [])
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(seen, [(self.editor, '2.3', '上の行\n' + COMP)])
        self.assertFalse(self.editor.tag_ranges('sel'))

    def test_no_conversion_runs_the_key_now(self):
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.assertFalse(self.a._commit_composition_first(self.key('F2'), Mock()))
        self.assertIsNone(getattr(self.a, '_pending_bracket_composition', None))

    def test_f2_targets_the_committed_word_not_the_row_above(self):
        rows = [];before = Mock(return_value=None)
        def units(row):
            rows.append((row, self.editor.index('insert')));return []
        self.a._editor_line_units = units;self.a._f2_last_word_before = before
        self.a._layout_is_unified = lambda:False;self.a.result_view = tk.Text(self.root)
        self.a._dropdown = None;self.a._quick_win = None;self.a._f2_cycle = None
        a, b, c = self.line_start()
        with a, b, c:
            self.assertEqual(self.a._on_f2_candidates(self.key('F5')), 'break')
            before.assert_not_called();self.assertEqual(rows, [])
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(rows, [(2, '2.3')])
        self.assertEqual(self.editor.get('1.0', 'end-1c'), '上の行\n' + COMP)

    def test_f1_quotes_after_the_committed_text(self):
        marks = []
        self.a.toggle_pick_mode = lambda:marks.append(self.editor.index('insert'))
        self.a._copy_focused_selection = lambda *args, **kwargs:False
        self.a._quick_win = None;self.root.focus_get = lambda:self.editor
        a, b, c = self.line_start()
        with a, b, c:
            self.assertEqual(self.a._on_pick_key(self.key('F1')), 'break')
            self.assertEqual(marks, [])
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(marks, ['2.3'])

    def test_bracket_key_during_the_candidate_commit_wraps_nothing(self):
        seen = []
        a, b, c = self.line_start()
        with a, b, c:
            self.a._commit_composition_first(self.key('F5'), lambda event:seen.append(True))
            self.assertEqual(self.a._on_f5_brackets(SimpleNamespace(widget=self.editor, keysym='F2', char='', state=0)), 'break')
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(self.editor.get('1.0', 'end-1c'), '上の行\n' + COMP)
        self.assertEqual(seen, [True])

    def test_owner_change_drops_the_key(self):
        seen = []
        a, b, c = self.line_start()
        with a, b, c:
            self.a._commit_composition_first(self.key('F2'), lambda event:seen.append(True))
            self.tab = {}   # another tab before the commit lands
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(seen, [])


    def test_f3_and_f4_commit_first_too(self):
        # 2026-10-22 うにさん: F3 は「変換しながら改行」、F4 は「変換のままペースト」になった。
        # F1・F2 と同じく、先に確定してから改行・貼り付けをする（貼り付けそのものは記録だけ）
        self.a._plain_shortcut = lambda event: True
        self.a._function_key_character = lambda event: None
        for name, sequence in (('_on_f3_return', '<Return>'), ('_on_f4_paste', '<<Paste>>')):
            with self.subTest(key=name):
                sent = []
                a, b, c = self.line_start()
                with a, b, c, patch.object(self.editor, 'event_generate',
                                           side_effect=lambda seq:sent.append((seq, self.editor.index('insert')))):
                    self.assertEqual(getattr(self.a, name)(self.key('F3')), 'break')
                    self.assertEqual(sent, [])                          # not while converting
                    self.wait(lambda:self.a._pending_bracket_composition is None)
                self.assertEqual(sent, [(sequence, '2.3')])             # after the committed text
                self.assertEqual(self.editor.get('1.0', 'end-1c'), '上の行\n' + COMP)

    def test_a_commit_that_never_arrives_says_so(self):
        self.a.status = Mock()
        with patch.object(ime_watch, 'composition_active', return_value=True), \
             patch.object(ime_watch, 'read_composition', return_value={'comp':COMP}), \
             patch.object(ime_watch, 'complete_composition', return_value=True):
            self.assertTrue(self.a._commit_composition_first(self.key('F1'), Mock()))
            self.assertIn('確定しています', self.a.status.config.call_args[1]['text'])
            self.a._pending_bracket_composition['until'] = 0
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertIn('届きませんでした', self.a.status.config.call_args[1]['text'])


if __name__ == '__main__':
    unittest.main()
