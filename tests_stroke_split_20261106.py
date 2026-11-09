# -*- coding: utf-8 -*-
"""One commit's keys split by its clauses, only when they fit exactly (2026-11-06). No window, no IME."""
import unittest

import stroke_split as S


def keys(text, t0=0, step=50):
    return [(k, t0 + n * step) for n, k in enumerate(text)]


class Kana(unittest.TestCase):
    def test_fits_exactly(self):
        # は る が き た = f . t @ g q（JIS かな）、空白・Enter が後ろ
        strokes = keys('f.t@gq') + [('', 400), ('', 500)]
        got = S.split(strokes, [], ['はるが', 'きた'], 'kana')
        self.assertEqual([''.join(k for k, _ in g[0] if k) for g in got], ['f.t@', 'gq'])
        self.assertEqual(got[1][0][-2:], (('', 400), ('', 500)))      # the conversion keys ride on the last clause

    def test_half_width_katakana_reading_from_the_ime(self):
        got = S.split(keys('f.t@gq'), [], ['ﾊﾙｶﾞ', 'ｷﾀ'], 'kana')
        self.assertIsNotNone(got)

    def test_small_kana_by_shift(self):
        # き ょ う = g (shift)9 4
        strokes = [('g', 0), ('9', 50), ('4', 100), ('f', 150)]
        got = S.split(strokes, [(40, 60)], ['きょう', 'は'], 'kana')
        self.assertEqual([[k for k, _ in g[0]] for g in got], [['g', '9', '4'], ['f']])
        self.assertEqual(got[0][1], ((40, 60),))
        self.assertEqual(got[1][1], ())

    def test_handakuten_and_long_vowel(self):
        # ぱ ー と = f [ ¥ s
        got = S.split(keys('f[¥s'), [], ['ぱー', 'と'], 'kana')
        self.assertEqual([[k for k, _ in g[0]] for g in got], [['f', '[', chr(165)], ['s']])

    def test_does_not_fit(self):
        self.assertIsNone(S.split(keys('f.t@gq'), [], ['はるが', 'きたな'], 'kana'))        # one kana more
        self.assertIsNone(S.split(keys('f.t@gq'), [], ['はるか', 'きた'], 'kana'))          # the voiced mark counts
        self.assertIsNone(S.split(keys('f.') + [('', 100)] + keys('t@gq', 200), [], ['はるが', 'きた'], 'kana'))   # a BackSpace inside
        self.assertIsNone(S.split(keys('@f.'), [], ['゛はる'], 'kana'))                       # a mark with nothing before

    def test_other_layouts_are_left_alone(self):
        self.assertIsNone(S.split(keys('f.t@gq'), [], ['はるが', 'きた'], 'kana', ('dvorak', 'standard', '', 'jis')))
        self.assertIsNone(S.split(keys('f.t@gq'), [], ['はるが', 'きた'], 'kana', ('qwerty_jis', 'standard', '', 'oyayubi')))
        self.assertIsNotNone(S.split(keys('f.t@gq'), [], ['はるが', 'きた'], 'kana', ('qwerty_jis', 'standard', '', 'jis')))


class Romaji(unittest.TestCase):
    def test_fits_exactly(self):
        got = S.split(keys('harugakita'), [], ['はるが', 'きた'], 'romaji')
        self.assertEqual([''.join(k for k, _ in g[0]) for g in got], ['haruga', 'kita'])

    def test_a_cut_that_is_not_decided_is_not_made(self):
        # 切れ目が字の途中（きゃ の ky｜a）にしか無い
        self.assertIsNone(S.split(keys('kyaku'), [], ['き', 'ゃく'], 'romaji'))

    def test_does_not_fit(self):
        self.assertIsNone(S.split(keys('harugakitq'), [], ['はるが', 'きた'], 'romaji'))   # a letter left over
        self.assertIsNone(S.split(keys('haru1'), [], ['はる'], 'romaji'))

    def test_small_tsu_cut(self):
        got = S.split(keys('kittewokau'), [], ['きってを', 'かう'], 'romaji')
        self.assertEqual([''.join(k for k, _ in g[0]) for g in got], ['kittewo', 'kau'])


class RomajiMarks(unittest.TestCase):
    def test_comma_period_and_long_vowel_keys(self):
        got = S.split(keys('sou,desu.'), [], ['そう、', 'です。'], 'romaji')
        self.assertEqual([''.join(k for k, _ in g[0]) for g in got], ['sou,', 'desu.'])
        got = S.split(keys('ra-mennwotaberu'), [], ['らーめんを', 'たべる'], 'romaji')
        self.assertEqual([''.join(k for k, _ in g[0]) for g in got], ['ra-mennwo', 'taberu'])

    def test_marks_that_do_not_fit(self):
        self.assertIsNone(S.split(keys('sou,desu.'), [], ['そう', 'です'], 'romaji'))        # the reading has no 、。
        self.assertIsNone(S.split(keys('sou;desu'), [], ['そう', 'です'], 'romaji'))         # ; is not read as anything
        self.assertIsNone(S.split(keys('ra-menn'), [], ['ら', 'めん'], 'romaji'))            # the reading has no ー

    def test_the_splitter_itself_has_no_switch(self):
        # CN_STROKE_SPLIT=0 is read by the caller (app._commit_strokes_for)
        self.assertIsNotNone(S.split(keys('sou,desu.'), [], ['そう、', 'です。'], 'romaji'))


class Other(unittest.TestCase):
    def test_unknown_method_or_nothing(self):
        self.assertIsNone(S.split(keys('abc'), [], ['あ', 'い'], 'english'))
        self.assertIsNone(S.split([], [], ['あ'], 'kana'))
        self.assertIsNone(S.split(keys('f'), [], [], 'kana'))


if __name__ == '__main__':
    unittest.main()
