# -*- coding: utf-8 -*-
"""Font preferences across normal, overview and quick-entry widgets."""
import json
import tkinter as tk
import tkinter.font as tkfont
import types
import unittest
from unittest.mock import Mock, patch, mock_open

import app
from settings import Settings, DEFAULT_EDITOR_FONT


class FontSettingsTests(unittest.TestCase):
    def test_load_valid_fonts_and_reject_damaged_values(self):
        for family, size, expected in (
                ('Yu Gothic', 18, ('Yu Gothic', 18)),
                ('', 0, DEFAULT_EDITOR_FONT),
                (None, True, DEFAULT_EDITOR_FONT),
                (['Yu Mincho'], '18', DEFAULT_EDITOR_FONT),
                ('Yu Gothic', 999999, ('Yu Gothic', 11))):
            settings = Settings()
            data = json.dumps(dict(editor_font_family=family, editor_font_size=size))
            with patch('settings.os.path.exists', return_value=True), \
                    patch('builtins.open', mock_open(read_data=data)):
                settings.load('synthetic-settings.json')
            self.assertEqual((settings.get('editor_font_family'),
                              settings.get('editor_font_size')), expected)


class FontTkTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a = self.a
        a.root = self.root
        a.settings = Settings()
        for name in ('editor', 'result_view', '_quick_text'):
            w = tk.Text(self.root, font=DEFAULT_EDITOR_FONT, undo=True)
            w.insert('1.0', '😀本文\t資料\n次の行')
            w.tag_add('sel', '1.0+1c', '1.0+3c')
            w.mark_set('insert', '2.2')
            w.edit_reset()
            setattr(a, name, w)
        a._syncing = False
        a._overview_pad = {}
        a._overview = None
        a._layout_is_unified = lambda: True
        a._adjust_quick_size = Mock()
        a._set_ime_font = Mock()
        a._schedule_whitespace_paint = Mock()
        a._font_size_var = tk.IntVar(master=self.root, value=11)
        a.editor_gutter = types.SimpleNamespace(font=None, redraw=Mock())
        a.result_gutter = types.SimpleNamespace(font=None, redraw=Mock())

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')

    def test_change_and_overview_restore_keeps_text_selection_and_quick_size(self):
        a = self.a
        family = tkfont.nametofont('TkFixedFont').actual('family')
        snapshots = [(w.get('1.0', 'end-1c'), tuple(map(str, w.tag_ranges('sel'))),
                      w.index('insert')) for w in a._whitespace_targets()]
        a._choose_editor_font(family, 18)
        self.root.update_idletasks()
        self.assertEqual(a._editor_font(), (family, 18))
        self.assertEqual(a.editor_gutter.font, (family, 18))
        self.assertEqual(a._font_size_var.get(), 18)
        quick_stops = a._quick_text.cget('tabs')
        a._overview_fonts(5)
        self.root.update_idletasks()
        self.assertEqual(tkfont.Font(font=a.editor.cget('font')).actual('size'), 5)
        self.assertEqual(tkfont.Font(font=a._quick_text.cget('font')).actual('size'), 18)
        self.assertEqual(a._quick_text.cget('tabs'), quick_stops)
        a._overview_fonts(None)
        self.root.update_idletasks()
        for w, before in zip(a._whitespace_targets(), snapshots):
            self.assertEqual(tkfont.Font(font=w.cget('font')).actual('size'), 18)
            self.assertEqual((w.get('1.0', 'end-1c'),
                              tuple(map(str, w.tag_ranges('sel'))),
                              w.index('insert')), before)
            with self.assertRaises(tk.TclError):
                w.edit_undo()
        a._choose_editor_font(*DEFAULT_EDITOR_FONT)
        self.root.update_idletasks()
        self.assertEqual(a._editor_font(), DEFAULT_EDITOR_FONT)
        self.assertEqual(tkfont.Font(font=a._quick_text.cget('font')).actual('size'), 11)

    def test_font_dialog_can_apply_and_reopen_without_duplicate_window(self):
        self.a._place_dialog = Mock()
        self.a.open_font_dialog()
        first = self.a._font_dialog
        self.a.open_font_dialog()
        self.assertIs(self.a._font_dialog, first)
        first.destroy()
        self.a.open_font_dialog()
        self.assertIsNot(self.a._font_dialog, first)
