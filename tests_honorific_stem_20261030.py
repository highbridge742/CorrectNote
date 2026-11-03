# -*- coding: utf-8 -*-
"""honorific_stem（お＋動詞の連用形＋する に同じ読みの普通名詞が入った所・2026-10-30）の試験。"""
import unittest

import honorific_stem as H


class HonorificStemTests(unittest.TestCase):
    def test_noun_with_a_common_verb_stem_reading_is_fixed(self):
        line = '傘は明日お菓子します'
        out = H.repair_line(line, {'corrected': line, 'changed': False})
        self.assertEqual(out['corrected'], '傘は明日お貸しします')

    def test_humble_forms_and_action_nouns_are_kept(self):
        for line in ('書類をお送りします', 'あとでお電話します', 'お茶しませんか', 'お世話します',
                     'お掃除します', 'お手伝いします', 'お届けいたします', 'お弁当します'):
            self.assertEqual(H.propose(line), [], line)

    def test_more_familiar_noun_is_only_marked(self):
        marks = H.propose('明日お酒します')
        self.assertEqual([m[2] for m in marks], [None])

    def test_without_suru_nothing_happens(self):
        self.assertEqual(H.propose('お菓子をいただきます'), [])


if __name__ == '__main__':
    unittest.main()
