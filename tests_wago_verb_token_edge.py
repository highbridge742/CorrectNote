"""wago_verb: 解析で1語の動詞を格子が途中で切った読み（かんが｜える）は置かない（作った例）。"""
import os
import unittest

import wago_verb as W


def _fix(t):
    return W.repair_line(t, {'original': t, 'corrected': t, 'changed': False}).get('corrected') or t


class TokenEdgeTest(unittest.TestCase):
    def test_split_inside_word_kept(self):
        self.assertEqual(_fix('かんがえる'), 'かんがえる')

    def test_whole_verb_still_kanji(self):
        self.assertEqual(_fix('よくかんがえる。'), 'よく考える。')


if __name__ == '__main__':
    unittest.main()
