# -*- coding: utf-8 -*-
"""ime_reconvert: 巻き込みの1字で 動詞＋た＋こと が 動詞＋漢数字の語 になった所を戻す（2026-11-08 手分けA）。例は作った文。
最後のクラスは correction_entry の案（_numerals_in_words・形式名詞）を入れたときだけ通る。"""
import unittest

import ime_reconvert as R


def _with(rec, fn):
    import kanji_guess
    kanji_guess.set_ime_readings_provider(lambda f: rec.get(f, []))
    try:
        return fn()
    finally:
        kanji_guess.set_ime_readings_provider(None)


class RollinVerbTail(unittest.TestCase):
    def test_rollin_into_numeral_word(self):
        # はなし＋ふ＋たこと（ふ は た の隣のキー）を IME が 話し二言 にした
        rec = {'話し二言': ['はなしふたこと'], '安心': ['あんしん']}
        got = _with(rec, lambda: R.propose('話し二言で安心した。', 'kana', None))
        self.assertIn((0, 4, '話したことで安心した。'), got)
        rec = {'見せ二言': ['みせふたこと']}
        self.assertIn((0, 4, '見せたことで'), _with(rec, lambda: R.propose('見せ二言で', 'kana', None)))

    def test_real_numeral_words_untouched(self):
        rec = {'彼': ['かれ'], '二言目': ['ふたことめ'], '文句': ['もんく'], '言う': ['いう']}
        self.assertEqual(_with(rec, lambda: [m for m in R.propose('彼は二言目には文句を言う。', 'kana', None) if m[2]]), [])
        rec = {'一言': ['ひとこと'], '言え': ['いえ'], '簡単': ['かんたん']}
        self.assertEqual(_with(rec, lambda: R.propose('一言で言えば簡単だ。', 'kana', None)), [])

    def test_no_record_no_fix(self):
        self.assertEqual(_with({}, lambda: [m for m in R.propose('話し二言で安心した。', 'kana', None) if m[2]]), [])

    def test_helpers(self):
        self.assertTrue(R._rollin_drop('はなしふたこと', 'はなしたこと'))
        self.assertFalse(R._rollin_drop('はなしふたこと', 'はなしふたと'))
        self.assertTrue(R._numeral_in_word('話し二言で', 2))
        self.assertFalse(R._numeral_in_word('二十人', 0))
        self.assertIn('伝えたこと', R._lattice_faces('つたえたこと'))


class EntryNumeralWord(unittest.TestCase):
    def test_numeral_inside_word(self):
        import correction_entry as CE
        self.assertTrue(CE._numerals_in_words('話し二言で', 2, 4))
        self.assertFalse(CE._numerals_in_words('二十度', 0, 2))
        self.assertFalse(CE._numerals_in_words('四m', 0, 1))


if __name__ == '__main__':
    unittest.main()
