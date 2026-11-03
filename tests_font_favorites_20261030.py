# -*- coding: utf-8 -*-
"""フォントのお気に入り（ピン・2026-10-30 うにさん）: ピンを付けたフォントは一覧の上に並び、線で区切った下の
全部の一覧にも残る。名前を押すと選び、ピンを押すとオンオフ。設定（font_favorites）に残る。"""
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from font_picker import FontList, PIN_W
from settings import Settings


class FontListTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.chosen, self.saved = [], []
        self.families = ['Arial', 'Meiryo', 'MS Gothic', 'Yu Gothic UI', 'Yu Mincho']
        self.list = FontList(self.root, self.families, ['Yu Mincho', 'No Such Font'], 'Meiryo',
                             on_select=self.chosen.append, on_favorites=self.saved.append)
        self.list.pack()
        self.root.update_idletasks()
        self.list.render()

    def tearDown(self):
        self.root.destroy()

    def click(self, family, section, on_pin):
        y0, y1, _, _ = next(r for r in self.list.rows if r[2] == family and r[3] == section)
        x = 5 if on_pin else PIN_W + 20
        y = (y0 + y1) // 2 - self.list.canvas.canvasy(0)
        return self.list._click(SimpleNamespace(x=x, y=y))

    def test_pinned_on_top_and_still_in_the_whole_list(self):
        pinned, rest = self.list.sections()
        self.assertEqual(pinned, ['Yu Mincho'])                 # a font not on this PC is left out
        self.assertEqual(rest, self.families)
        self.assertEqual([(r[2], r[3]) for r in self.list.rows][:2], [('Yu Mincho', 'pinned'), ('Arial', 'all')])

    def test_pin_toggles_and_name_selects(self):
        self.click('Arial', 'all', on_pin=True)
        self.assertEqual(self.saved[-1], ['Yu Mincho', 'Arial'])
        self.assertEqual(self.list.sections()[0], ['Arial', 'Yu Mincho'])   # the list's order (2026-10-31)
        self.click('Yu Mincho', 'pinned', on_pin=True)             # off from the top section
        self.assertEqual(self.saved[-1], ['Arial'])
        self.click('MS Gothic', 'all', on_pin=False)
        self.assertEqual(self.chosen, ['MS Gothic'])
        self.assertEqual(self.list.selected, 'MS Gothic')
        self.assertEqual(self.saved[-1], ['Arial'])                # selecting does not pin

    def test_typing_narrows_both_sections(self):
        self.list.set_filter('yu')
        self.assertEqual(self.list.sections(), (['Yu Mincho'], ['Yu Gothic UI', 'Yu Mincho']))
        self.list.set_filter('')
        self.assertEqual(len(self.list.sections()[1]), 5)


class EnglishNameTests(unittest.TestCase):
    # 2026-10-31 うにさん「最初から入っている Yu Mincho が、リスト内にないんだけどなんで？」: Windows は 游明朝 の名で並べる
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_alias_is_shown_matched_and_the_setting_finds_its_row(self):
        from font_picker import listed_name
        families = ['Arial', '游明朝', 'Yu Gothic UI']
        fonts = FontList(self.root, families, [], '游明朝', on_select=lambda n: None, on_favorites=lambda n: None,
                         aliases={'游明朝': 'Yu Mincho'})
        fonts.pack(); self.root.update_idletasks(); fonts.render()
        texts = [fonts.canvas.itemcget(i, 'text') for i in fonts.canvas.find_all()
                 if fonts.canvas.type(i) == 'text']
        self.assertIn('游明朝', texts)
        self.assertNotIn('Yu Mincho', texts)                  # shown as listed (2026-10-31); the alias only matches
        fonts.set_filter('yu min')
        self.assertEqual(fonts.sections()[1], ['游明朝'])
        self.assertEqual(listed_name(self.root, 'Arial', families), 'Arial')
        self.assertEqual(listed_name(self.root, 'No Such Font', families), 'No Such Font')

    def test_english_aliases_only_for_names_this_pc_lists_otherwise(self):
        import tkinter.font as tkfont
        from font_picker import english_aliases
        families = sorted(set(tkfont.families(self.root)))
        aliases = english_aliases(self.root, families)
        self.assertTrue(all(name in families for name in aliases))
        self.assertTrue(all(alias.casefold() != name.casefold() for name, alias in aliases.items()))


class ReopenTests(unittest.TestCase):
    def test_a_pinned_choice_is_shown_in_the_pinned_group(self):
        # 2026-10-31 うにさん「ピン付きのフォントで決定して、フォントウインドウを開きなおしたら、上のピンのグループの
        # ほうをフォーカスした状態にする」
        root = tk.Tk(); root.withdraw()
        try:
            families = ['F%03d' % i for i in range(200)]
            fonts = FontList(root, families, ['F150'], 'F150', on_select=lambda n: None, on_favorites=lambda n: None,
                             height=100)
            fonts.pack(); root.update_idletasks(); fonts.render()
            fonts.canvas.yview_moveto(0.5)
            fonts.see('F150')
            self.assertEqual(fonts.canvas.canvasy(0), 0)          # the pinned row at the top is in view
            fonts.see('F120')                                      # not pinned: its row in the whole list
            self.assertGreater(fonts.canvas.canvasy(0), 0)
        finally:
            root.destroy()


class DefaultFallbackTests(unittest.TestCase):
    # 2026-10-31 うにさん「Noto Serifがない場合、メイリオ、その次に游明朝、その次にWindowsの判断」
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_chain(self):
        from unittest.mock import patch
        import font_picker as F
        for present, want in ((('Noto Serif', 'メイリオ'), 'Noto Serif'), (('メイリオ', '游明朝'), 'メイリオ'),
                              (('游明朝',), '游明朝'), ((), 'Noto Serif')):
            with self.subTest(present=present), patch.object(F, 'installed', lambda root, f: f in present):
                self.assertEqual(F.default_family(self.root), want)

    def test_installed_tells_a_stand_in_from_a_real_font(self):
        import tkinter.font as tkfont
        from font_picker import installed
        real = next(f for f in tkfont.families(self.root) if not f.startswith('@'))
        self.assertTrue(installed(self.root, real))
        self.assertFalse(installed(self.root, 'No Such Font Family 2026'))

    def test_the_app_uses_the_chain_only_for_the_default_name(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import app
        import font_picker as F
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.settings = Settings()
        with patch.object(F, 'installed', lambda root, f: f in ('メイリオ', 'Arial')):
            self.assertEqual(a._editor_font(), ('メイリオ', app.EDITOR_FONT[1]))
            a.settings.set('editor_font_family', 'Arial')
            self.assertEqual(a._editor_font()[0], 'Arial')     # a chosen font is never replaced


class FavoritesSettingTests(unittest.TestCase):
    def test_saved_and_read_back_as_names(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'settings.json')
            s = Settings(path)
            self.assertIn('Noto Serif', s.get('font_favorites'))     # うにさんの選んだ11（2026-10-31）
            self.assertEqual(len(s.get('font_favorites')), 11)
            s.set('font_favorites', ['Meiryo', 'Yu Mincho']); s.save()
            self.assertEqual(Settings(path).get('font_favorites'), ['Meiryo', 'Yu Mincho'])
            Path(path).write_text(json.dumps({'font_favorites': 'broken'}), encoding='utf-8')
            self.assertEqual(len(Settings(path).get('font_favorites')), 11)   # a damaged value: the defaults


if __name__ == '__main__':
    unittest.main()
