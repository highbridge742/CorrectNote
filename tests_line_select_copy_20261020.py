# -*- coding: utf-8 -*-
"""Shift+Space selects the line when nothing is selected, and copies the selection when there
is one (2026-10-20 うにさん「選択が無いときの Shift+Space は行全体を選ぶ。選択があるとき（ドラッグ
での範囲選択でも、行選択でも）の Shift+Space は、その選択範囲をコピーする」), through the usual
copy (with B/I/U/S when the text has them). Nothing is counted any more, so analysis running in
between (tags, the cursor moved, other keys) does not matter. The Edit menu has 「行を選択
Shift+Space」 just above 「コピー」, whose shortcut text is 「選択してF1 / 行選択してShift+Space」.
2026-10-22 うにさん「Shift+上下で、行の途中までを選択した状態でShift+Spaceしても行選択しない。この
場合は途中までの選択した行を行全体選択する」: a selection with an end inside a line is first widened
to the whole lines it touches; only a whole-line selection is copied (so a dragged partial selection
now needs a second press to copy).
Tk's clipboard is replaced inside the interpreter, so the Windows clipboard is not touched."""
import inspect
import unittest
from unittest.mock import Mock
import tkinter as tk

import app
from tests_tk_keys import deliver_key


class LineSelectCopyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.root.tk.eval('rename clipboard line_select_saved_clipboard; set ::fake {}; '
                          'proc clipboard {op args} {if {$op eq "get"} {return $::fake}; '
                          'if {$op eq "append"} {append ::fake [lindex $args end]}; '
                          'if {$op eq "clear"} {set ::fake {}}}')
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root)
        a.result_view = tk.Text(self.root)
        a.status = Mock()
        a._rich_copy = Mock(return_value=None)          # plain copy through Tk (the fake above)
        for w in (a.editor, a.result_view):
            w.insert('1.0', '最初の行😀\n  二行目の本文　\n\n末尾')
            a._install_line_selection_keys(w)
        self.root.update()

    def tearDown(self):
        self.root.tk.eval('rename clipboard {}; rename line_select_saved_clipboard clipboard')
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')

    def clipboard(self):
        return self.root.tk.getvar('::fake')

    def press(self, w):
        deliver_key(w, '<Shift-space>', 'space', 32, state=1)

    def test_no_selection_selects_the_line_then_copies(self):
        for w in (self.a.editor, self.a.result_view):
            with self.subTest(pane=str(w)):
                self.root.tk.setvar('::fake', '')
                w.tag_remove('sel', '1.0', 'end'); w.mark_set('insert', '2.3')
                self.press(w)
                self.assertEqual(w.get('sel.first', 'sel.last'), '  二行目の本文　')
                self.assertEqual(self.clipboard(), '')           # nothing selected before: selects only
                self.press(w)
                self.assertEqual(self.clipboard(), '  二行目の本文　')
                self.assertEqual(w.get('sel.first', 'sel.last'), '  二行目の本文　')   # kept
                self.root.tk.setvar('::fake', '')
                self.press(w)                                     # again: copies again
                self.assertEqual(self.clipboard(), '  二行目の本文　')

    def test_a_partial_selection_is_widened_to_whole_lines_then_copied(self):
        for w in (self.a.editor, self.a.result_view):
            for first, last, whole in (('1.2', '2.3', '最初の行😀\n  二行目の本文　'),   # dragged / Shift+Down
                                       ('2.3', '2.5', '  二行目の本文　'),               # inside one line
                                       ('1.0', '2.3', '最初の行😀\n  二行目の本文　'),   # starts at a line head
                                       ('2.4', '4.0', '  二行目の本文　\n'),             # ends at the next head
                                       ('1.0 lineend -1c', '2.0 lineend', '最初の行😀\n  二行目の本文　')):
                with self.subTest(pane=str(w), first=first, last=last):
                    self.root.tk.setvar('::fake', '')
                    w.tag_remove('sel', '1.0', 'end')
                    w.tag_add('sel', first, last); w.mark_set('insert', last)
                    self.press(w)
                    self.assertEqual(w.get('sel.first', 'sel.last'), whole)
                    self.assertEqual(self.clipboard(), '')                   # widened, not copied
                    self.assertEqual(w.index('insert'), w.index('sel.last'))
                    self.press(w)
                    self.assertEqual(self.clipboard(), whole)                # whole lines: copied
                    self.assertEqual(w.get('sel.first', 'sel.last'), whole)

    def test_whole_line_selections_are_copied_as_they_are(self):
        w = self.a.editor
        for first, last in (('1.0', '1.0 lineend'), ('1.0', '3.0'), ('2.0', '4.end')):
            with self.subTest(first=first, last=last):
                self.root.tk.setvar('::fake', '')
                w.tag_remove('sel', '1.0', 'end'); w.tag_add('sel', first, last)
                chosen = w.get('sel.first', 'sel.last')
                self.press(w)
                self.assertEqual(self.clipboard(), chosen)
                self.assertEqual(w.get('sel.first', 'sel.last'), chosen)

    def test_analysis_in_between_does_not_matter(self):
        # What analysis does between two presses: other tags, the cursor moved, other keys
        w = self.a.editor
        w.mark_set('insert', '1.2')
        self.press(w)
        w.tag_add('suspect', '1.0', '1.3'); w.tag_add('fixed', '2.0', '2.4')
        w.mark_set('insert', '4.0')
        deliver_key(w, '<KeyPress>', 'Right', 39)
        self.press(w)
        self.assertEqual(self.clipboard(), '最初の行😀')

    def test_empty_line_has_nothing_to_copy(self):
        w = self.a.editor
        w.mark_set('insert', '3.0')
        self.press(w); self.press(w)
        self.assertEqual(self.clipboard(), '')
        self.assertFalse(w.tag_ranges('sel'))

    def test_menu_select_line_then_copy(self):
        a = self.a
        a.editor.focus_force(); self.root.update()
        a.editor.mark_set('insert', '4.1')
        a._select_line_from_menu()
        self.assertEqual(a.editor.get('sel.first', 'sel.last'), '末尾')
        self.assertEqual(self.clipboard(), '')
        a._select_line_from_menu()
        self.assertEqual(self.clipboard(), '末尾')

    def test_edit_menu_items(self):
        source = inspect.getsource(app.CorrectNoteApp)
        select = source.index("m_edit.add_command(label='行を選択', accelerator='Shift+Space',")
        copy = source.index("m_edit.add_command(label='コピー', accelerator='選択してF1 / 行選択してShift+Space',")
        self.assertLess(select, copy)
        self.assertNotIn("add_command(label=", source[select + 10:copy])   # nothing in between
        self.assertNotIn('LINE_SELECT_PRESS_TAG', source)                  # nothing counted


if __name__ == '__main__':
    unittest.main()
