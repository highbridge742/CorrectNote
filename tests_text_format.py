# -*- coding: utf-8 -*-
"""Bold/italic/underline/strikethrough presentation tags on the input pane."""
import tkinter as tk
import tkinter.font as tkfont
import unittest
from unittest.mock import Mock

import app
from pos_font import POS_FONT_TAGS, font_size
from session import new_tab, clean_text_styles
from settings import Settings, DEFAULT_EDITOR_FONT
from text_format import STYLE_TAGS, font_tag, install, project, _stable
from tests_tk_keys import deliver_key


class TextFormatTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root = self.root
        self.a.settings = Settings()
        self.a._schedule_session_save = Mock()
        self.w = tk.Text(self.root, font=DEFAULT_EDITOR_FONT, undo=True)
        self.w.pack()
        self.w.insert('1.0', '😀資料を確認する。\n次の行です')
        self.w.edit_reset()
        self.f = install(self.a, self.w)

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root', 'w', 'f')

    def names(self, index):
        return self.w.tag_names(index)

    def tagged(self, key):
        # tag_rangesの数値indexはWindowsのTk 8.6でUTF-16列になり、
        # そのままgetへ渡すと絵文字の後ろで1文字ずれるので文字数の位置へ直す。
        ranges = self.w.tag_ranges(STYLE_TAGS[key])
        self.assertEqual(len(ranges), 2, ranges)
        return self.w.get(*(_stable(self.w, index) for index in ranges))

    def test_selection_toggles_each_style_without_touching_text_or_undo(self):
        w = self.w
        w.tag_add('sel', '1.0+1c', '1.0+3c')
        text = w.get('1.0', 'end-1c')
        for key in ('bold', 'italic', 'underline', 'overstrike'):
            self.f.toggle(key)
            self.assertIn(STYLE_TAGS[key], self.names('1.0+1c'))
            self.assertIn(STYLE_TAGS[key], self.names('1.0+2c'))
            self.assertNotIn(STYLE_TAGS[key], self.names('1.0+3c'))
            self.assertTrue(self.f.active(key))
        self.assertEqual(w.tag_cget(STYLE_TAGS['underline'], 'underline'), '1')
        self.assertEqual(w.tag_cget(STYLE_TAGS['overstrike'], 'overstrike'), '1')
        self.assertIn(font_tag(None, 'bi'), self.names('1.0+1c'))
        for key in ('bold', 'italic', 'underline', 'overstrike'):
            self.f.toggle(key)
            self.assertNotIn(STYLE_TAGS[key], self.names('1.0+1c'))
        self.assertNotIn(font_tag(None, 'bi'), self.names('1.0+1c'))
        self.assertEqual(w.get('1.0', 'end-1c'), text)
        # The eight style changes are now Ctrl+Z steps of their own (2026-10-14
        # うにさん「ボールドや下線などの編集を履歴として持つ」); the text never changes.
        for key in reversed(('bold', 'italic', 'underline', 'overstrike')):
            w.edit_undo()
            self.assertIn(STYLE_TAGS[key], self.names('1.0+1c'))
        for key in reversed(('bold', 'italic', 'underline', 'overstrike')):
            w.edit_undo()
            self.assertNotIn(STYLE_TAGS[key], self.names('1.0+1c'))
        self.assertEqual(w.get('1.0', 'end-1c'), text)
        with self.assertRaises(tk.TclError):
            w.edit_undo()
        self.assertEqual(self.errors, [])

    def test_undo_and_redo_take_style_changes_in_turn_with_typing(self):
        w = self.w
        text = w.get('1.0', 'end-1c')
        w.edit_separator()
        w.tag_add('sel', '1.0', '1.0+2c'); self.f.toggle('bold'); w.tag_remove('sel', '1.0', 'end')
        w.insert('end', 'XY'); w.edit_separator()
        bold = lambda: STYLE_TAGS['bold'] in self.names('1.0')
        w.edit_undo(); self.assertEqual(w.get('1.0', 'end-1c'), text); self.assertTrue(bold())
        w.edit_undo(); self.assertEqual(w.get('1.0', 'end-1c'), text); self.assertFalse(bold())
        w.edit_redo(); self.assertTrue(bold()); self.assertEqual(w.get('1.0', 'end-1c'), text)
        w.edit_redo(); self.assertEqual(w.get('1.0', 'end-1c'), text + 'XY'); self.assertTrue(bold())
        # A new edit after an undone style ends its redo, as for text.
        w.edit_undo(); w.edit_undo(); self.assertFalse(bold())
        w.insert('end', 'Z')
        with self.assertRaises(tk.TclError):
            w.edit_redo()
        self.assertFalse(bold())
        self.assertEqual(self.errors, [])

    def test_partly_bold_selection_becomes_all_bold(self):
        w = self.w
        w.tag_add(STYLE_TAGS['bold'], '1.0+1c', '1.0+2c')
        w.tag_add('sel', '1.0+1c', '1.0+4c')
        self.assertFalse(self.f.active('bold'))
        self.f.toggle('bold')
        self.assertEqual(self.tagged('bold'), '資料を')

    def test_typing_after_toggle_uses_the_style_until_the_cursor_moves(self):
        w = self.w
        w.mark_set('insert', '2.end')
        self.f.toggle('bold')
        self.assertTrue(self.f.active('bold'))
        w.insert('insert', '太字')
        self.assertEqual(self.tagged('bold'), '太字')
        self.f.toggle('bold')
        w.insert('insert', '普通')
        self.assertEqual(self.tagged('bold'), '太字')
        self.f.toggle('underline')
        self.f.moved()
        w.insert('insert', '後')
        self.assertFalse(w.tag_ranges(STYLE_TAGS['underline']))

    def test_shortcuts_toggle_styles(self):
        w = self.w
        for sequence, keysym, key in (('<Control-b>', 'b', 'bold'), ('<Control-Key-2>', '2', 'bold'),
                                      ('<Control-i>', 'i', 'italic'), ('<Control-Key-3>', '3', 'italic'),
                                      ('<Control-u>', 'u', 'underline'), ('<Control-Key-4>', '4', 'underline'),
                                      ('<Control-Key-5>', '5', 'overstrike')):
            w.tag_remove('sel', '1.0', 'end')
            w.tag_add('sel', '2.0', '2.2')
            before = STYLE_TAGS[key] in self.names('2.0')
            deliver_key(w, sequence, keysym, 0, state=4)
            self.assertEqual(STYLE_TAGS[key] in self.names('2.0'), not before, sequence)
        self.assertEqual(w.get('1.0', 'end-1c'), '😀資料を確認する。\n次の行です')

    def test_bold_inside_pos_sized_word_keeps_the_pos_size(self):
        w = self.w
        self.a.settings.set('pos_font_multipliers', {'名詞': 1.5})
        self.f.refresh_fonts()
        w.tag_add(POS_FONT_TAGS['名詞'], '1.0+1c', '1.0+3c')
        w.tag_add('sel', '1.0+2c', '1.0+4c')
        self.f.toggle('bold')
        bold_noun = font_tag('名詞', 'b')
        self.assertIn(bold_noun, self.names('1.0+2c'))
        self.assertNotIn(bold_noun, self.names('1.0+3c'))
        self.assertIn(font_tag(None, 'b'), self.names('1.0+3c'))
        size = tkfont.Font(root=self.root, font=w.tag_cget(bold_noun, 'font')).actual()
        self.assertEqual(size['size'], font_size(DEFAULT_EDITOR_FONT[1], 1.5))
        self.assertEqual(size['weight'], 'bold')

    def test_capture_and_restore_round_trip_after_emoji(self):
        w = self.w
        w.tag_add(STYLE_TAGS['bold'], '1.0+1c', '1.0+3c')
        w.tag_add(STYLE_TAGS['overstrike'], '1.0+5c', '2.0+2c')
        captured = self.f.capture(w.get('1.0', 'end-1c').split('\n'))
        self.assertEqual(captured, {'bold': [[1, 1, 1, 3]], 'overstrike': [[1, 5, 2, 2]]})
        tab = new_tab(text=w.get('1.0', 'end-1c'), text_styles=captured)
        self.assertEqual(tab['text_styles'], captured)
        self.f.restore({})
        self.assertFalse(w.tag_ranges(STYLE_TAGS['bold']))
        self.f.restore(tab['text_styles'])
        self.assertEqual(self.tagged('bold'), '資料')
        self.assertEqual(self.tagged('overstrike'), '認する。\n次の')
        self.assertIn(font_tag(None, 'b'), self.names('1.0+1c'))

    def test_styles_are_shown_on_the_read_only_correction_pane(self):
        r = tk.Text(self.root, font=DEFAULT_EDITOR_FONT)
        r.insert('1.0', '😀資料を確認しました。\n次の行です')
        r.configure(state='disabled')
        mirror = install(self.a, r, editable=False)
        calls = []
        self.f.listeners.append(lambda: calls.append(1))
        self.w.tag_add('sel', '1.0+4c', '1.0+8c')
        self.f.toggle('bold')
        self.assertTrue(calls)
        self.w.tag_remove('sel', '1.0', 'end')
        self.w.tag_add('sel', '2.0', '2.2')
        self.f.toggle('underline')
        self.f.mirror_to(mirror)
        bold = r.tag_ranges(STYLE_TAGS['bold'])
        self.assertEqual(r.get(*(_stable(r, i) for i in bold)), '確認しました')
        self.assertIn(font_tag(None, 'b'), r.tag_names('1.0+4c'))
        under = r.tag_ranges(STYLE_TAGS['underline'])
        self.assertEqual(r.get(*(_stable(r, i) for i in under)), '次の')
        self.assertEqual(r.get('1.0', 'end-1c'), '😀資料を確認しました。\n次の行です')
        # Removing the style in the memo removes it from the copy.
        self.f.toggle('underline')
        self.f.mirror_to(mirror)
        self.assertFalse(r.tag_ranges(STYLE_TAGS['underline']))
        self.assertEqual(r.cget('state'), 'disabled')

    def test_projection_follows_corrected_words(self):
        source = ['私わ学生です', 'きしゃの資料', '同じ行']
        target = ['私は学生です', '貴社の資料', '同じ行']
        styles = {'bold': [[1, 1, 1, 2], [2, 0, 3, 2]], 'italic': [[1, 2, 1, 4]]}
        self.assertEqual(project(styles, source, target),
                         {'bold': [[1, 1, 1, 2], [2, 0, 2, 5], [3, 0, 3, 2]],
                          'italic': [[1, 2, 1, 4]]})
        self.assertEqual(project({'bold': [[1, 0, 1, 2]]}, ['きしゃ'], ['貴社']),
                         {'bold': [[1, 0, 1, 2]]})
        self.assertEqual(project({'bold': [[5, 0, 5, 2]]}, ['a'], ['a']), {})
        self.assertEqual(project({'bold': [[1, 0, 1, 1], [1, 1, 1, 2]]}, ['ab'], ['ab']),
                         {'bold': [[1, 0, 1, 2]]})

    def test_session_cleaning_drops_damaged_ranges(self):
        self.assertEqual(clean_text_styles({'bold': [[1, 2, 1, 1], [0, 0, 1, 1], [1, 0, 1, 2], 'x'],
                                            'unknown': [[1, 0, 1, 1]], 'italic': 5}),
                         {'bold': [[1, 0, 1, 2]]})
        self.assertNotIn('text_styles', new_tab(text='abc'))


if __name__ == '__main__':
    unittest.main()
