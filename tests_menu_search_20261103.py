# -*- coding: utf-8 -*-
"""編集メニューの「ブラウザを開いて検索」（作った例・ブラウザは開かない）。"""
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import app as app_module
import f3_search
import ui_lang_en

App = app_module.CorrectNoteApp


class Item(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.editor = tk.Text(self.root)
        self.editor.insert('1.0', '資料 を作る')
        self.other = tk.Text(self.root)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label='ブラウザを開いて検索')
        self.a = NS(root=self.root, editor=self.editor, result_view=self.other, status=Mock(), _edit_menu=self.menu, _edit_search_index=0)
        self.a._focused_selected_text = lambda: App._focused_selected_text(self.a)

    def color(self):
        return str(self.menu.entrycget(0, 'foreground'))

    def test_grey_with_no_selection_but_still_pressable(self):
        App._refresh_edit_search_item(self.a)
        self.assertEqual(self.color(), app_module.MUTED)
        self.assertEqual(self.menu.entrycget(0, 'state'), 'normal')

    def test_ordinary_color_with_a_selection(self):
        App._refresh_edit_search_item(self.a)
        self.editor.tag_add('sel', '1.0', '1.2')
        App._refresh_edit_search_item(self.a)
        self.assertEqual(self.color(), '')

    def test_the_other_pane_selection_counts(self):
        self.other.insert('1.0', '資料'); self.other.tag_add('sel', '1.0', '1.2')
        self.assertEqual(App._focused_selected_text(self.a), '資料')

    def test_press_with_no_selection_opens_the_top(self):
        with patch('webbrowser.open', return_value=True) as opened:
            App._search_from_menu(self.a)
        opened.assert_called_once_with('https://www.google.com/')

    def test_press_with_a_selection_searches_it(self):
        self.editor.tag_add('sel', '1.0', '1.2')
        with patch('webbrowser.open', return_value=True) as opened:
            App._search_from_menu(self.a)
        opened.assert_called_once_with('https://www.google.com/search?q=%E8%B3%87%E6%96%99')

    def test_browser_refusing_is_said(self):
        with patch('webbrowser.open', return_value=False):
            App._search_from_menu(self.a)
        self.assertIn('開けません', self.a.status.config.call_args[1]['text'])

    def test_english_labels(self):
        for label in ('無選択でF3 / Enter', 'ブラウザを開いて検索', '選択してF3'):
            self.assertIn(label, ui_lang_en.__dict__[[k for k, v in ui_lang_en.__dict__.items() if isinstance(v, dict) and '改行' in v][0]])


if __name__ == '__main__':
    unittest.main()
