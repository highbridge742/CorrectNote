# -*- coding: utf-8 -*-
"""The 再変換 and 説明書 buttons, and what goes first when the window is narrow (2026-10-23 うにさん).

- 再変換 opens the candidates as F5 does, left of the quote button, shortened to 「再」.
- 説明書 opens the manual, left of the layout buttons on the right.
- Saved settings from before: both appear (shown by default) in their places.
- Narrow: names shorten first; then the manual goes, then the brackets from the right (one stays),
  then B/I/U/S, then the ruler; wider again brings them back in reverse.
The real toolbar at many widths: tools_local/emphasis_20261023/probe_toolbar.py."""
import unittest
from types import SimpleNamespace

import app
from toolbar_preferences import normalized, IDS


OLD_SAVED = [key for key in IDS if key not in ('reconvert', 'manual')]


class ToolbarButtonTests(unittest.TestCase):
    def test_saved_settings_from_before_get_both_buttons_shown(self):
        order, hidden = normalized(OLD_SAVED, [])
        self.assertEqual(order[order.index('reconvert') + 1], 'quote')
        self.assertEqual(order[order.index('manual') + 1], 'layout_split')
        self.assertEqual(order[-3:], ['manual', 'layout_split', 'layout_unified'])
        self.assertFalse({'reconvert', 'manual'} & hidden)

    def test_what_goes_first_when_narrow(self):
        order, hidden = normalized(None, None)
        widgets = {key: SimpleNamespace(key=key) for key in order}
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._toolbar_preferences = SimpleNamespace(order=order, hidden=hidden, widgets=widgets)
        keys = [w.key for w in a._toolbar_drop_order()]
        self.assertEqual(keys, ['manual', 'bracket_quotes', 'bracket_black', 'bracket_double', 'bracket_single',
                                'format_bold', 'ruler'])                 # （） stays; I/U/S are hidden by default
        # Turned on by the user, the other B/I/U/S buttons go too, from the right
        a._toolbar_preferences.hidden = set()
        keys = [w.key for w in a._toolbar_drop_order()]
        self.assertEqual(keys[5:], ['format_overstrike', 'format_underline', 'format_italic', 'format_bold', 'ruler'])

    def test_the_reconvert_button_does_what_f5_does(self):
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        seen = []
        a.root = SimpleNamespace(focus_get=lambda: None)
        a.editor = SimpleNamespace(focus_set=lambda: seen.append('focus'))
        a.result_view = object()
        a._on_f2_candidates = lambda event: seen.append((event.widget is a.editor, event.keysym))
        a._reconvert_from_button()
        self.assertEqual(seen, ['focus', (True, a.CANDIDATE_KEY)])


class ShortNamesTests(unittest.TestCase):
    """2026-10-23 うにさん: when narrow, 箇条書き→箇条, 簡易入力→簡易, 単語帳→単語 — after the other short names,
    before any button is hidden; wider again brings the names back."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk(); self.root.attributes('-alpha', 0); self.root.geometry('2000x60+10000+100')
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a._toolbar = tk.Frame(self.root); a._toolbar.pack(fill='x')
        names = {'bookmark_prev_btn': '▲ 前のブックマーク', 'bookmark_next_btn': '▼ 次のブックマーク',
                 'layout_split_btn': '左右に並べる', 'layout_unified_btn': '1つにまとめる', 'reconvert_btn': '再変換',
                 'pick_mode_btn': 'クリックして引用', 'bulk_insert_btn': '一括挿入', 'list_mode_btn': '箇条書き',
                 'quick_input_btn': '簡易入力', 'word_book_btn': '単語帳'}
        for name, label in names.items():
            button = tk.Button(a._toolbar, text=label, font=('Yu Gothic UI', 9), padx=8)
            button.pack(side='left', padx=(4, 0))
            setattr(a, name, button)
        self.dropped = []
        a._drop_toolbar_buttons = lambda: self.dropped.append(a._toolbar_label_stage)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def fit(self, width):
        self.root.geometry('%dx60' % width); self.root.update()
        self.a._fit_toolbar_labels()
        return [self.a.list_mode_btn.cget('text'), self.a.quick_input_btn.cget('text'), self.a.word_book_btn.cget('text')]

    def test_short_names_come_last_and_go_back(self):
        a = self.a
        self.assertEqual(self.fit(2000), ['箇条書き', '簡易入力', '単語帳'])
        self.assertEqual(a._toolbar_label_stage, 0)
        full = sum(a._toolbar_width_of(w) for w in a._toolbar.pack_slaves())
        # Just narrower than all stage 1-3 names: the three stay; much narrower: stage 4
        self.fit(full - 10)
        self.assertLess(a._toolbar_label_stage, 4)
        self.assertEqual(a.list_mode_btn.cget('text'), '箇条書き')
        self.assertEqual(self.fit(300), ['箇条', '簡易', '単語'])
        self.assertEqual(a._toolbar_label_stage, 4)
        self.assertEqual(a.pick_mode_btn.cget('text'), '引用')          # the earlier stages are shortened too
        self.assertEqual(self.dropped[-1], 4)                          # hiding is decided after the names
        self.assertEqual(self.fit(2000), ['箇条書き', '簡易入力', '単語帳'])
        self.assertEqual(a.pick_mode_btn.cget('text'), 'クリックして引用')


if __name__ == '__main__':
    unittest.main()
