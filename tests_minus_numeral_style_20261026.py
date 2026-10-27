# -*- coding: utf-8 -*-
"""A minus sign right before digits takes the numeral (数詞) colour (2026-10-26 うにさん
「数字の前のマイナスを、数詞のフォントカラーに含める」).

-5・－５・−3.2・-1,234.5 are numerals as a whole; the hyphen in 7-3, 2026-10-26 and a-1 stays a symbol;
a minus on its own stays a symbol; the right-click 品詞判定 names the same row as the colour.
Only the display changes — the correction does not look at these runs.
"""
import unittest

import explain
from pos_font import spans


def kinds(text, pos='記号:一般'):
    """Each character of ``text`` with the row its colour takes."""
    got = [None] * len(text)
    for kind, a, z in spans(text, [(text, pos, '', 0, len(text))]):
        for i in range(a, z):
            got[i] = kind
    return got


class MinusNumeralTests(unittest.TestCase):
    def test_minus_before_digits_is_a_numeral(self):
        for text in ('-5', '－５', '−3.2', '-1,234.5', '﹣7'):
            self.assertEqual(set(kinds(text)), {'数詞'}, text)

    def test_hyphens_between_numbers_or_letters_stay_symbols(self):
        self.assertEqual(kinds('7-3'), ['数詞', '記号', '数詞'])
        got = kinds('2026-10-26')
        self.assertEqual([got[4], got[7]], ['記号', '記号'])
        self.assertEqual(kinds('a-1')[1], '記号')
        self.assertEqual(kinds('3.5-2')[3], '記号')

    def test_a_minus_alone_stays_a_symbol(self):
        self.assertEqual(kinds('-'), ['記号'])
        self.assertEqual(kinds('－ '), ['記号', '記号'])
        self.assertEqual(kinds('-a')[0], '記号')

    def test_inside_a_sentence(self):
        text = '気温は-5度'
        tokens = [('気温', '名詞:一般', 'キオン', 0, 2), ('は', '助詞:係助詞', 'ハ', 2, 3),
                  ('-', '記号:一般', '', 3, 4), ('5', '名詞:数', '', 4, 5), ('度', '名詞:接尾:助数詞', 'ド', 5, 6)]
        got = {text[a:z]: kind for kind, a, z in spans(text, tokens)}
        self.assertEqual(got['-'], '数詞')
        self.assertEqual(got['5'], '数詞')
        self.assertEqual(got['気温'], '名詞')

    def test_right_click_says_what_the_colour_shows(self):
        for text in ('-5', '－５', '−3.2', '-1,234.5'):
            self.assertEqual(explain.pos_lines(text), ['数詞'], text)
        # the minus alone, by its neighbours
        self.assertEqual(explain.pos_lines('-', prev_text='は', next_text='5'), ['数詞'])
        self.assertEqual(explain.pos_lines('-', prev_text='7', next_text='3'), ['記号'])
        self.assertEqual(explain.pos_lines('-'), ['記号'])
        self.assertIn('- ＝ 記号', explain.pos_lines('7-3'))


if __name__ == '__main__':
    unittest.main()
