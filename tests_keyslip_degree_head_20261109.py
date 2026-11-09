# -*- coding: utf-8 -*-
"""keyslip_window._degree_head: 程度の語＋名詞＋助詞＋述語（大変｜頭 を 悩ませた）を1キー違いの窓にしない
（2026-11-09 手分けB）。例は作った文。記録なし。"""
import os
import unittest

import kanji_guess
import keyslip_window as K


def _p(line):
    kanji_guess.set_ime_readings_provider(lambda s: [])
    return K.propose(line)


class DegreeHead(unittest.TestCase):
    def test_degree_noun_kept(self):
        for line in ('仕事のことで大変頭を悩ませた', '準備するのに大変頭を使った'):
            self.assertEqual(_p(line), [], line)

    def test_switch(self):
        os.environ['CN_KEYSLIP_DEGREE_HEAD'] = '0'
        try:
            import morphology
            toks = list(morphology.tokenize('仕事のことで大変頭を悩ませた'))
            i = next(k for k, t in enumerate(toks) if t.surface == '大変')
            self.assertFalse(K._degree_head('仕事のことで大変頭を悩ませた', toks, i, i + 2))
            self.assertTrue(_p('仕事のことで大変頭を悩ませた'))   # 切ると前のとおり紫が付く
        finally:
            del os.environ['CN_KEYSLIP_DEGREE_HEAD']

    def test_needs_predicate(self):
        import morphology
        line = '大変頭。'
        toks = list(morphology.tokenize(line))
        self.assertFalse(K._degree_head(line, toks, 0, 2))


if __name__ == '__main__':
    unittest.main()
