# -*- coding: utf-8 -*-
"""colloquial_adj: くだけた形の形容詞を元の形に戻して読む（2026-11-09 batch441）。作り例だけ。"""
import unittest

import colloquial_adj as C
import wago_verb as W


class T(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(C.normalize('すげえなあ')[0], 'すごいなあ')
        self.assertEqual(C.normalize('でけえ')[0], 'でかい')
        self.assertEqual(C.normalize('ありがてえ')[0], 'ありがたい')
        self.assertEqual(C.normalize('わからねえ')[0], 'わからない')

    def test_keep(self):
        for t in ('いいねえ', 'そうだねえ', 'まえにいく', 'ねえさん', 'かえる'):
            self.assertEqual(C.normalize(t)[0], t)

    def test_tokens(self):
        import morphology
        t = C.tokenize_with('すげえなあ', morphology.tokenize)
        self.assertEqual((t[0].surface, t[0].pos, t[0].base_form), ('すげえ', '形容詞', 'すごい'))

    def test_verb_after(self):
        line = 'すげえはやくはしる'
        self.assertEqual(W.repair_line(line, {'corrected': line, 'changed': False})['corrected'], 'すげえはやく走る')


if __name__ == '__main__':
    unittest.main()
