# -*- coding: utf-8 -*-
"""Colour emoji are drawn by the CPU, not handed to the graphics card (2026-10-20: a PC
running CorrectNote crashed in its graphics driver). The pictures stay as they were drawn with
the default (GPU) target — same place, same colours — and drawing stays about as fast, for the
emoji in the text and for a word book button's line. Nothing is shown on screen."""
import sys
import time
import unittest

import emoji_color

CASES = [  # (text, px, width, height, bg, fg, family, leading)
    ('😀', 15, 20, 20, '#ffffff', None, None, False),           # an emoji in the text
    ('👍🏽', 20, 26, 26, '#1e1e1e', None, None, False),           # with a skin tone, dark theme
    ('🇯🇵', 28, 36, 36, '#f0f0ed', None, None, False),           # a flag
    ('旧登録😀メモ', 15, 120, 24, '#f0f0ed', '#1c2b2d', 'Yu Gothic UI', True),   # word book button
    ('☕ 休憩 🍰', 15, 120, 24, '#2b2b2b', '#e8e8e8', 'Yu Gothic UI', True),
]


def pixels(ppm):
    head_end = ppm.index(b'\n') + 1
    return ppm[head_end:]


@unittest.skipUnless(sys.platform == 'win32', 'DirectWrite')
class SoftwareEmojiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.software = emoji_color.EmojiRenderer()
            cls.default = emoji_color.EmojiRenderer(target_type=0)
        except Exception as error:
            raise unittest.SkipTest('DirectWrite unavailable: %s' % error)

    def draw(self, renderer, case):
        text, px, w, h, bg, fg, family, leading = case
        return renderer.render(text, px, w, h, bg, fg=fg, family=family, leading=leading)

    def test_the_app_draws_in_software(self):
        self.assertEqual(emoji_color.EmojiRenderer.TARGET_TYPE, 1)

    def test_pictures_match_the_default_target(self):
        for case in CASES:
            with self.subTest(text=case[0]):
                a, b = pixels(self.draw(self.software, case)), pixels(self.draw(self.default, case))
                self.assertEqual(len(a), len(b))
                diffs = [abs(x - y) for x, y in zip(a, b)]
                changed = sum(1 for d in diffs if d > 24) / len(diffs)
                # anti-aliasing at glyph edges may differ by a shade; nothing moves or changes colour
                self.assertLess(changed, 0.02, (case[0], max(diffs), changed))
                bg = case[4]
                self.assertNotEqual(set(a), {int(bg[i:i + 2], 16) for i in (1, 3, 5)}, 'something was drawn')

    def test_drawing_stays_fast(self):
        def timed(renderer):
            for case in CASES:                      # warm the text formats and glyph caches
                self.draw(renderer, case)
            start = time.perf_counter()
            for _ in range(40):
                for case in CASES:
                    self.draw(renderer, case)
            return (time.perf_counter() - start) / (40 * len(CASES))
        soft, gpu = timed(self.software), timed(self.default)
        print('\nper picture: software %.2f ms, default %.2f ms' % (soft * 1000, gpu * 1000))
        self.assertLess(soft, max(gpu * 3, gpu + 0.004), (soft, gpu))


if __name__ == '__main__':
    unittest.main()
