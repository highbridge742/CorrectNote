# -*- coding: utf-8 -*-
"""Pronouns have their own row in the per-POS size and colour (2026-10-26 うにさん
「フォントサイズカラーの代名詞も独立する。1.2倍、緑明るい」).

Japanese pronouns (名詞:代名詞) and English ones (en_pos code O) both take it; other nouns stay 名詞;
the defaults are 1.2× and a bright green (緑・明るい on dark, the same green as it reads on white);
a settings file from before takes these new defaults (not its 名詞 values); changing 代名詞 leaves the
other rows as they were; the right-click 品詞判定 names the same row.
"""
import re
import unittest

import en_pos
import pos_font
from pos_font import (PRONOUN, POS_CATEGORIES, POS_DIALOG_ROWS, POS_FONT_TAGS, color_defaults,
                      display_color, major_pos, normalize_colors, normalize_multipliers, palette_color,
                      spans)


class PronounRowTests(unittest.TestCase):
    def english(self, text):
        words = [m.span() for m in re.finditer(r"[A-Za-z]+", text)]
        return {text[a:z]: kind for (a, z), kind in zip(words, en_pos.categories(text, words))}

    def test_japanese_pronouns_take_their_own_row(self):
        tokens = [('これ', '名詞:代名詞:一般', 'コレ', 0, 2), ('は', '助詞:係助詞', 'ハ', 2, 3),
                  ('彼', '名詞:代名詞:一般', 'カレ', 3, 4), ('の', '助詞:連体化', 'ノ', 4, 5),
                  ('本', '名詞:一般', 'ホン', 5, 6)]
        got = {'これは彼の本'[a:z]: kind for kind, a, z in spans('これは彼の本', tokens)}
        self.assertEqual(got['これ'], PRONOUN)
        self.assertEqual(got['彼'], PRONOUN)
        self.assertEqual(got['本'], '名詞')
        self.assertEqual(major_pos('名詞:代名詞'), PRONOUN)
        self.assertEqual(major_pos('名詞:サ変接続'), '名詞（サ変）')
        self.assertEqual(major_pos('名詞:数'), '数詞')

    def test_english_pronouns_take_their_own_row(self):
        if not en_pos.available():
            self.skipTest('en_pos.json.gz is not here')
        got = self.english('He said it was a book.')
        self.assertEqual(got['He'], PRONOUN, got)
        self.assertEqual(got['it'], PRONOUN, got)
        self.assertEqual(got['book'], '名詞', got)

    def test_the_row_comes_after_meishi_and_tags_keep_their_numbers(self):
        keys = [k for k, _l in POS_DIALOG_ROWS]
        self.assertEqual(keys[keys.index('名詞') + 1], PRONOUN)
        self.assertEqual(dict(POS_DIALOG_ROWS)['名詞'], '名詞')
        self.assertEqual(keys[-1], '英字')
        self.assertEqual(POS_CATEGORIES[-1], PRONOUN)
        self.assertEqual(POS_FONT_TAGS['名詞'], 'pos_font_0')
        self.assertEqual(POS_FONT_TAGS['冠詞'], 'pos_font_17')

    def test_defaults_are_1_2_and_bright_green(self):
        self.assertEqual(normalize_multipliers(None)[PRONOUN], 1.2)
        self.assertEqual(color_defaults(True)[PRONOUN], palette_color('緑', '明るい'))
        self.assertEqual(color_defaults(False)[PRONOUN], display_color(palette_color('緑', '明るい'), False))
        import settings
        self.assertEqual(settings.DEFAULTS['pos_font_multipliers'][PRONOUN], 1.2)

    def test_settings_from_before_take_the_new_defaults(self):
        old_sizes = {'名詞': 1.5, '連体詞': 1.3}
        old_colors = {'名詞': '#123456'}
        self.assertEqual(normalize_multipliers(old_sizes)[PRONOUN], 1.2)
        self.assertEqual(normalize_colors(old_colors)[PRONOUN], palette_color('緑', '明るい'))
        self.assertEqual(normalize_colors(old_colors, dark=False)[PRONOUN], color_defaults(False)[PRONOUN])
        import settings
        values = {'pos_font_multipliers': {}}
        settings._move_to_new_pos_defaults(values, {'pos_font_colors': {'名詞': '#123456'}})
        self.assertEqual(values['pos_font_colors'][PRONOUN], palette_color('緑', '明るい'))
        self.assertEqual(values['pos_font_colors_light'][PRONOUN], color_defaults(False)[PRONOUN])

    def test_changing_pronouns_leaves_the_others(self):
        before_sizes = normalize_multipliers({'名詞': 1.4})
        before_colors = normalize_colors({'名詞': '#abcdef'})
        sizes = normalize_multipliers({'名詞': 1.4, PRONOUN: 1.6})
        colors = normalize_colors({'名詞': '#abcdef', PRONOUN: '#ff0000'})
        self.assertEqual(sizes[PRONOUN], 1.6)
        self.assertEqual(colors[PRONOUN], '#ff0000')
        for key in POS_CATEGORIES:
            if key != PRONOUN:
                self.assertEqual(sizes[key], before_sizes[key], key)
                self.assertEqual(colors[key], before_colors[key], key)

    def test_right_click_names_the_same_row(self):
        if not en_pos.available():
            self.skipTest('en_pos.json.gz is not here')
        import explain
        self.assertEqual(explain.pos_lines('it'), ['代名詞（英語）'])


if __name__ == '__main__':
    unittest.main()
