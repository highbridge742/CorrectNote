# -*- coding: utf-8 -*-
"""batch418: お＋語の区切りの紫・形式名詞の紫・御/お の書き方違いを迷いに数えない（kana_lattice_place）。"""
import os
import unittest

import kana_lattice_place as K


class LatticeOFormal(unittest.TestCase):
    def _doubts(self, text):
        return K.propose(text, None, None)[1]

    def test_formal_noun_no_purple(self):
        t = '弟は寝たふりをした。'
        self.assertFalse([d for d in self._doubts(t) if t[d[0]:d[1]] == 'ふり'])

    def test_o_prefix_no_purple(self):
        t = '店員がおじぎをした。'
        self.assertFalse([d for d in self._doubts(t) if 'じぎ' in t[d[0]:d[1]]])

    def test_honorific_variant_dedupe(self):
        import last_keystroke as LK
        faces, _own = K._everyday_faces('おじぎ', None, None, LK)
        self.assertFalse(any(f.startswith('御') for f in faces) and any(f.startswith('お') for f in faces))


if __name__ == '__main__':
    unittest.main()
