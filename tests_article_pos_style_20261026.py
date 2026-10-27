# -*- coding: utf-8 -*-
"""English articles (a / an / the) have their own row in the per-POS size and colour (2026-10-26 うにさん
「品詞ごとのフォントサイズカラーの、冠詞を独立した項目にする」).

They are judged as determiners (en_pos code D) first and told apart by the word; the defaults look as 連体詞
did; a settings file from before keeps how articles looked (they take its 連体詞 values); changing 冠詞 leaves
the other rows as they were.
"""
import unittest

import en_pos
import pos_font
from pos_font import (ARTICLE, POS_CATEGORIES, POS_DIALOG_ROWS, POS_FONT_TAGS, color_defaults,
                      normalize_colors, normalize_multipliers, spans)


class ArticleRowTests(unittest.TestCase):
    def runs(self, text):
        import re
        words = [m.span() for m in re.finditer(r"[A-Za-z]+", text)]
        return {text[a:z]: kind for (a, z), kind in zip(words, en_pos.categories(text, words))}

    def test_articles_take_their_own_row(self):
        if not en_pos.available():
            self.skipTest('en_pos.json.gz is not here')
        got = self.runs('The cat saw a dog and an owl. This box is mine.')
        for word in ('The', 'a', 'an'):
            self.assertEqual(got[word], ARTICLE, (word, got))
        self.assertEqual(got['This'], '連体詞', got)       # other determiners stay where they were
        self.assertEqual(got['cat'], '名詞', got)

    def test_the_row_comes_after_rentaishi_and_tags_keep_their_numbers(self):
        keys = [k for k, _l in POS_DIALOG_ROWS]
        self.assertEqual(keys[keys.index('連体詞') + 1], ARTICLE)
        self.assertEqual(keys[-1], '英字')
        # 代名詞 came after 冠詞 (2026-10-26), so 冠詞 is next to last
        self.assertEqual(POS_CATEGORIES[-2:], (ARTICLE, '代名詞'))
        self.assertEqual(POS_FONT_TAGS['連体詞'], 'pos_font_8')
        self.assertEqual(dict(POS_DIALOG_ROWS)['連体詞'], '連体詞・限定詞')

    def test_defaults_look_as_rentaishi(self):
        self.assertEqual(normalize_multipliers(None)[ARTICLE], normalize_multipliers(None)['連体詞'])
        for dark in (True, False):
            self.assertEqual(color_defaults(dark)[ARTICLE], color_defaults(dark)['連体詞'])

    def test_settings_from_before_keep_the_look(self):
        old_sizes = {'連体詞': 1.3, '名詞': 1.1}
        old_colors = {'連体詞': '#123456'}
        self.assertEqual(normalize_multipliers(old_sizes)[ARTICLE], 1.3)
        self.assertEqual(normalize_colors(old_colors)[ARTICLE], '#123456')
        self.assertEqual(normalize_colors(old_colors, dark=False)[ARTICLE], '#123456')

    def test_changing_articles_leaves_the_others(self):
        before_sizes = normalize_multipliers({'連体詞': 1.2})
        before_colors = normalize_colors({'連体詞': '#abcdef'})
        sizes = normalize_multipliers({'連体詞': 1.2, ARTICLE: 1.6})
        colors = normalize_colors({'連体詞': '#abcdef', ARTICLE: '#ff0000'})
        self.assertEqual(sizes[ARTICLE], 1.6)
        self.assertEqual(colors[ARTICLE], '#ff0000')
        for key in POS_CATEGORIES:
            if key != ARTICLE:
                self.assertEqual(sizes[key], before_sizes[key], key)
                self.assertEqual(colors[key], before_colors[key], key)

    def test_settings_migration_keeps_rentaishi_colour_for_articles(self):
        import settings
        values = {'pos_font_multipliers': {}}
        settings._move_to_new_pos_defaults(values, {'pos_font_colors': {'連体詞': '#123456'}})
        self.assertEqual(values['pos_font_colors'][ARTICLE], '#123456')
        self.assertEqual(values['pos_font_colors_light'][ARTICLE], values['pos_font_colors_light']['連体詞'])


if __name__ == '__main__':
    unittest.main()
