# -*- coding: utf-8 -*-
"""前後の語で決める英語の取り違え（en_context.py・2026-10-23）。

うにさん「英文の強化もはじめます」（2026-10-23）。打ち違いが別の正しい語に
なったもの（come form・next weak）と、同じ音の語の取り違え（their is・
let me now）を、前後の語との組の多さで直す。正しい英文・名前・コード・
日本語混じりは触らない。例はすべて作った文。
"""
import unittest

import en_context
import en_space
import en_typo


def apply(line):
    out = line
    for s, e, fix in sorted(en_space.find_missing_spaces(line), reverse=True):
        out = out[:s] + fix + out[e:]
    return out


@unittest.skipUnless(en_typo.available() and en_context.available(),
                     'en_freq.json.gz and en_context.json.gz required')
class EnglishContextTest(unittest.TestCase):
    def test_slips_onto_real_words(self):
        cases = {
            'I will come form the station.': 'I will come from the station.',
            'This is better then the old one.':
                'This is better than the old one.',
            'He want out with his friends.': 'He went out with his friends.',
            'Could you send me the fist page?':
                'Could you send me the first page?',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)

    def test_same_sound(self):
        cases = {
            'Their is a small shop near the park.':
                'There is a small shop near the park.',
            'I will be their in an hour.': 'I will be there in an hour.',
            'Did you here the news?': 'Did you hear the news?',
            'Nice to meat you.': 'Nice to meet you.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)

    def test_unknown_words_by_neighbours(self):
        # 巻き込みは上下斜めの隣も（日本語と同じ。2026-10-23 うにさん）
        self.assertEqual(apply('The library is a quiet plafce to study.'),
                         'The library is a quiet place to study.')
        # 重複補正 OFF の2回打ちは、ほかの語にもしない
        self.assertEqual(apply('Please do not ommit the last line.'),
                         'Please do not ommit the last line.')

    def test_lone_small_i(self):
        # 行頭の i も、後ろが動詞・副詞・短縮形なら I（式の i はそのまま）
        self.assertEqual(apply("i don't know yet."), "I don't know yet.")
        self.assertEqual(apply('i advise you to rest.'), 'I advise you to rest.')
        self.assertEqual(apply('i is the loop variable'), 'i is the loop variable')

    def test_correct_english_is_left(self):
        for line in (
                'I like the color of your new bag.',
                'The movie starts in ten minutes.',
                'Where are you now?',
                'He passed the exam last week.',
                'Ill be there in an hour.',
                'Hasan said hi.',
                'tsar and odor',
                'Return None if the list is empty.',
                'Ask Mira Holt about the form.',
                'The struct has x, y and z.',
                'I think "form" is the word you want.',
                '明日の meeting で review する',
        ):
            with self.subTest(line=line):
                self.assertEqual(
                    [f for f in en_context.fixes(line)], [])

    def test_judged_by_both_neighbours(self):
        # an unseen pair on either side keeps the word
        self.assertIsNone(en_context.best('xqzv', 'form', 'the'))
        self.assertEqual(en_context.best('come', 'form', 'the'), 'from')
        self.assertIsNone(en_context.best(None, 'form', None))

    def test_spelling_variants(self):
        self.assertTrue(en_context._variant('color', 'colour'))
        self.assertTrue(en_context._variant('center', 'centre'))
        self.assertFalse(en_context._variant('form', 'from'))


if __name__ == '__main__':
    unittest.main()
