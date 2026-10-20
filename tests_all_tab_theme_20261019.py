# -*- coding: utf-8 -*-
"""The all-tab search results follow the appearance theme (2026-10-19 うにさん「全タブ検索の
結果を、外見配色に合わせてください」). The list is a ttk.Treeview, which _restyle_widget cannot
recolour, so it has its own style, set again on every theme change."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk

import app
import appearance

SOURCE = Path(app.__file__).read_text(encoding='utf-8')


def method_source(name):
    tree = ast.parse(SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SOURCE, node)
    raise AssertionError(name)


class AllTabThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def palettes(self):
        for theme in appearance.THEME_NAMES:
            pal, dark = appearance.theme_palette(theme, app.LIGHT_PALETTE, app.DARK_PALETTE,
                                                 app._STANDARD_FIXED_FG)
            yield theme, pal

    def test_every_theme_colours_the_list(self):
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        style = ttk.Style(self.root)
        name = app.CorrectNoteApp.ALL_TAB_STYLE
        seen = set()
        for theme, pal in self.palettes():
            with patch.multiple(app, **{k: pal[k] for k in app._PALETTE_KEYS}):
                a._configure_all_tab_style()
            got = (style.lookup(name, 'background'), style.lookup(name, 'fieldbackground'),
                   style.lookup(name, 'foreground'), style.lookup(name, 'background', ['selected']),
                   style.lookup(name + '.Heading', 'background'), style.lookup(name + '.Heading', 'foreground'))
            self.assertEqual(got, (pal['PANEL'], pal['PANEL'], pal['INK'], pal['EDITOR_SEL_BG'],
                                   pal['BG'], pal['INK']), theme)
            seen.add(got)
        self.assertGreater(len(seen), 1)          # the themes really differ

    def test_the_list_uses_the_style_and_a_theme_change_sets_it_again(self):
        ensure = method_source('_ensure_all_tab_results')
        self.assertIn('self._configure_all_tab_style()', ensure)
        self.assertIn('style=self.ALL_TAB_STYLE', ensure)
        self.assertIn('self._configure_all_tab_style()', method_source('_apply_theme'))

    def test_buttons_are_painted_like_the_find_window(self):
        ensure = method_source('_ensure_all_tab_results')
        self.assertIn('bg=PANEL, fg=INK', ensure)
        self.assertIn('activebackground=ACCENT', ensure)
        # every widget colour in the window comes from the palette (no fixed colours)
        self.assertNotRegex(ensure, r"(bg|fg|background|foreground)\s*=\s*['\"]#")


@unittest.skipUnless(__import__('sys').platform == 'win32', 'Windows ttk theme')
class AllTabPixelTests(unittest.TestCase):
    """The colours really reach the screen (2026-10-20 うにさん: in the dark theme the list, its
    heading and the scrollbar stayed white — Windows' own ttk parts ignore colours). A small
    window is shown for a moment at the top left, and its pixels are read from the screen."""

    def screen_pixels(self, widget, points):
        import ctypes
        from ctypes import wintypes as W
        u = ctypes.WinDLL('user32'); g = ctypes.WinDLL('gdi32')
        u.GetDC.restype = ctypes.c_void_p; u.GetDC.argtypes = [ctypes.c_void_p]
        u.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        g.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]; g.GetPixel.restype = W.DWORD
        x0, y0 = widget.winfo_rootx(), widget.winfo_rooty()
        dc = u.GetDC(None)
        try:
            out = {}
            for name, (x, y) in points.items():
                c = g.GetPixel(dc, x0 + x, y0 + y)
                out[name] = (c & 255, (c >> 8) & 255, (c >> 16) & 255)
            return out
        finally:
            u.ReleaseDC(None, dc)

    def test_list_heading_rows_and_scrollbar_are_coloured(self):
        import time
        def rgb(colour):
            return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
        for theme in ('light', 'dark'):
            pal = app.LIGHT_PALETTE if theme == 'light' else app.DARK_PALETTE
            root = tk.Tk()
            try:
                root.overrideredirect(True); root.attributes('-topmost', True)
                root.geometry('420x220+0+0')
                a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
                with patch.multiple(app, **{k: pal[k] for k in app._PALETTE_KEYS}):
                    a._configure_all_tab_style()
                frame = tk.Frame(root); frame.pack(fill='both', expand=True)
                tree = ttk.Treeview(frame, columns=('a',), show='headings', style=a.ALL_TAB_STYLE)
                tree.heading('a', text='見出し')
                for i in range(2):
                    tree.insert('', 'end', values=('行%d' % i,))
                scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview, style=a.ALL_TAB_SCROLL_STYLE)
                scroll.pack(side='right', fill='y'); tree.pack(side='left', fill='both', expand=True)
                root.update(); time.sleep(.3); root.update()
                w, h = tree.winfo_width(), tree.winfo_height()
                got = self.screen_pixels(tree, {'heading': (w // 4, 4), 'row': (w // 4, 32),
                                                'empty': (w // 2, h - 6)})
                # nothing to scroll: the thumb fills the bar
                got.update(self.screen_pixels(scroll, {'thumb': (scroll.winfo_width() // 2,
                                                                scroll.winfo_height() // 2)}))
            finally:
                root.destroy()
            want = {'heading': rgb(pal['BG']), 'row': rgb(pal['PANEL']), 'empty': rgb(pal['PANEL']),
                    'thumb': rgb(pal['RULE'])}
            for part, colour in want.items():
                self.assertLessEqual(max(abs(x - y) for x, y in zip(got[part], colour)), 12,
                                     (theme, part, got[part], colour))


if __name__ == '__main__':
    unittest.main()
