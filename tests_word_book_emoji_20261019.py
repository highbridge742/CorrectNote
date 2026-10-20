# -*- coding: utf-8 -*-
"""Emoji in the word book are shown in colour (2026-10-19 うにさん「単語帳に絵文字を追加すると
色がない」). Tk draws button text in black and white, so a word with emoji gets an image of the
same line drawn by DirectWrite (letters in the theme's ink, emoji in colour); the button keeps
its text. Words without emoji stay plain text."""
import sys
import unittest
import tkinter as tk

import emoji_color


@unittest.skipUnless(sys.platform == 'win32', 'DirectWrite')
class WordBookEmojiTests(unittest.TestCase):
    def setUp(self):
        if emoji_color.renderer() is None:
            self.skipTest('DirectWrite unavailable')
        self.root = tk.Tk(); self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def colours(self, image):
        w, h = image.width(), image.height()
        seen = set()
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                r, g, b = image.get(x, y)
                if max(r, g, b) - min(r, g, b) > 60:       # clearly coloured, not grey
                    seen.add((r // 32, g // 32, b // 32))
        return seen

    def test_line_image_has_colour_only_for_emoji(self):
        font = ('Yu Gothic UI', 11)
        image = emoji_color.line_image(self.root, '旧登録😀', font, '#1c2b2d', '#f0f0ed', 24)
        self.assertIsNotNone(image)
        self.assertGreater(image.width(), 30)
        self.assertTrue(self.colours(image), 'the emoji is drawn in colour')
        self.assertIsNone(emoji_color.line_image(self.root, '単語だけ', font, '#1c2b2d', '#f0f0ed', 24))

    def test_letters_take_the_theme_ink(self):
        # dark theme: light letters on a dark background (not black on dark)
        image = emoji_color.line_image(self.root, 'あああ😀', ('Yu Gothic UI', 11), '#e6e4dd', '#25292d', 24)
        light = sum(1 for y in range(image.height()) for x in range(image.width() // 2)
                    if sum(image.get(x, y)) > 450)
        self.assertGreater(light, 5)

    def test_word_book_buttons_use_it(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        import word_book
        book = word_book.WordBook.__new__(word_book.WordBook)
        book.app = SimpleNamespace(_editor_font=lambda: ('Yu Gothic UI', 11), root=self.root,
                                   _start_word_book_add=Mock())
        book.colors = lambda: ('#f0f0ed', '#1c2b2d', '#3366aa')
        book.sets = [['旧登録😀', '単語'], [], [], []]; book.active_set = 0
        book.width = 200
        book.window = tk.Toplevel(self.root); book.window.withdraw()
        book.header = tk.Frame(book.window); book.minimize_button = tk.Button(book.header)
        book.canvas = tk.Canvas(book.window); book.scroll = tk.Scrollbar(book.window)
        book.rows = tk.Frame(book.canvas)
        book.render()
        emoji_button, plain_button = book.buttons
        self.assertTrue(str(emoji_button.cget('image')))
        self.assertEqual(emoji_button.cget('text'), '旧登録😀')     # the text is kept
        self.assertFalse(str(plain_button.cget('image')))


if __name__ == '__main__':
    unittest.main()
