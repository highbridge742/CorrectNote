# -*- coding: utf-8 -*-
"""How quote mode, the chosen tab and the bulk insert box look (2026-10-23 うにさん).

- 引用モードのボタン: ライトの配色では、オンの間は地を ACCENT・字を PANEL に反転（ダークは今のまま）。
  オンの間はメモ欄・簡易入力の地を PANEL から ACCENT へ QUOTE_TINT_PERCENT ％寄せる（Text の地だけ）
- 選んでいるタブ: 上辺に ACCENT の線
- 一括挿入の文字列欄: 周りと違う地と枠、空のあいだは薄い字の案内（値には入らない）
Pictures of all six colour schemes: tools_local/emphasis_20261023/probe_quote_tabs.py. Withdrawn root."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import tkinter as tk

import app, appearance


class QuoteModeTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, bg=app.PANEL); a._quick_text = tk.Text(self.root, bg=app.PANEL)
        a.pick_mode_btn = tk.Button(self.root, bg=app.PANEL, fg=app.INK, relief='flat')

    def tearDown(self):
        self.root.destroy()

    def test_light_schemes_invert_the_button_and_tint_the_memo(self):
        a = self.a
        a._theme_dark = False
        a._show_quote_mode(True)
        b = a.pick_mode_btn
        self.assertEqual((b.cget('bg'), b.cget('fg'), b.cget('relief')), (app.ACCENT, app.PANEL, 'sunken'))
        tint = appearance.mix(app.PANEL, app.ACCENT, a.QUOTE_TINT_PERCENT / 100.0)
        self.assertEqual((a.editor.cget('bg'), a._quick_text.cget('bg')), (tint, tint))
        a._show_quote_mode(False)
        self.assertEqual((b.cget('bg'), b.cget('fg'), b.cget('relief')), (app.PANEL, app.INK, 'flat'))
        self.assertEqual((a.editor.cget('bg'), a._quick_text.cget('bg')), (app.PANEL, app.PANEL))

    def test_dark_schemes_keep_the_button_and_still_tint(self):
        a = self.a
        a._theme_dark = True
        a._show_quote_mode(True)
        b = a.pick_mode_btn
        self.assertEqual((b.cget('bg'), b.cget('fg'), b.cget('relief')), (app.PANEL, app.ACCENT, 'sunken'))
        self.assertNotEqual(a.editor.cget('bg'), app.PANEL)

    def test_no_tint_at_zero(self):
        a = self.a
        a._theme_dark = False; a.QUOTE_TINT_PERCENT = 0
        a._show_quote_mode(True)
        self.assertEqual(a.editor.cget('bg'), app.PANEL)


class TabLineTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root; a.tab_bar = tk.Frame(self.root)
        a.session = SimpleNamespace(tabs=[{}, {}, {}], active=1)
        a._tab_label_text = lambda tab, active: 'メモ'
        a._queue_tab_reveal = lambda: None
        for name in ('_switch_tab', '_close_tab', '_on_tab_press', '_on_tab_drag_motion', '_on_tab_drag_end',
                     '_scroll_tab_bar', '_tab_hover_hint', '_on_tab_right_press', '_on_tab_right_release', 'new_file'):
            setattr(a, name, Mock())

    def tearDown(self):
        self.root.destroy()

    def test_the_chosen_tab_has_an_accent_line_on_top(self):
        a = self.a
        a._rebuild_tab_bar(a.session.tabs, 1)
        lines = [w['line'] for w in a._tab_widgets]
        self.assertEqual([l.cget('bg') for l in lines], [app.BG, app.ACCENT, app.BG])
        self.assertEqual(int(lines[1].cget('height')), a.TAB_ACTIVE_LINE)
        a.session.active = 2
        a._refresh_tab_bar()
        self.assertEqual([w['line'].cget('bg') for w in a._tab_widgets], [app.BG, app.BG, app.ACCENT])


class BulkInsertFieldTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    # The dialog is transient to the withdrawn root, so it is never mapped here: the hint is
    # checked by whether it is placed in the box.
    def open(self, saved=''):
        import bulk_insert
        settings = {'bulk_insert_text': saved}
        editor = tk.Text(self.root)
        a = SimpleNamespace(root=self.root, settings=SimpleNamespace(get=settings.get, set=settings.__setitem__,
                                                                     save=lambda: None),
                            editor=editor, _set_window_icons_win32=lambda win: None,
                            _place_dialog=lambda win, w, h: win.geometry('+10000+10000'))
        dialog = bulk_insert.BulkInsertDialog(a, lambda: (app.PANEL, app.INK, app.ACCENT))
        dialog._draw_preview = lambda: None
        dialog.open(); dialog.window.attributes('-alpha', 0); self.root.update()
        return dialog

    def test_the_box_looks_like_an_input_and_shows_a_hint_while_empty(self):
        import bulk_insert
        dialog = self.open()
        self.assertNotEqual(dialog.text.cget('bg'), app.PANEL)
        self.assertEqual(int(dialog.text.cget('highlightthickness')), 1)
        self.assertTrue(dialog.placeholder.place_info())
        self.assertEqual(dialog.placeholder.cget('text'), bulk_insert.PLACEHOLDER)
        self.assertEqual(dialog.text.get('1.0', 'end-1c'), '')           # the hint is not the value
        dialog.text.insert('1.0', '★'); dialog.text.event_generate('<KeyRelease>'); self.root.update()
        self.assertFalse(dialog.placeholder.place_info())
        dialog.text.delete('1.0', 'end'); dialog.text.event_generate('<KeyRelease>'); self.root.update()
        self.assertTrue(dialog.placeholder.place_info())
        dialog.window.destroy()

    def test_no_hint_when_text_is_kept_from_last_time(self):
        dialog = self.open('、')
        self.assertFalse(dialog.placeholder.place_info())
        dialog.window.destroy()

    def test_the_colours_stand_apart_in_every_scheme(self):
        import bulk_insert
        for theme in appearance.THEME_ORDER:
            pal, dark = appearance.theme_palette(theme, app.LIGHT_PALETTE, app.DARK_PALETTE, app._STANDARD_FIXED_FG)
            field, edge, hint = bulk_insert.input_field_colors(pal['PANEL'], pal['INK'])
            with self.subTest(theme=theme):
                self.assertNotEqual(field, pal['PANEL'])
                self.assertNotEqual(edge, field)
                self.assertNotEqual(hint, field)


if __name__ == '__main__':
    unittest.main()
