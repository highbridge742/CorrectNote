# -*- coding: utf-8 -*-
"""batch427: かなだけの行の和語の動詞を漢字に置く（wago_verb・うに 2026-11-09 カード「動詞は漢字」）。作った例。"""
import os
import unittest

import wago_verb as W


def run(s):
    return W.repair_line(s, {'corrected': s})['corrected']


class WagoVerb(unittest.TestCase):
    def test_verb_to_kanji(self):
        self.assertEqual(run('ゆうはんをたべた'), 'ゆうはんを食べた')

    def test_frame_choice(self):
        self.assertEqual(run('てがみをかきます'), 'てがみを書きます')

    def test_kana_verbs_stay(self):
        for s in ('ここにいてください', 'ではそれをいただきます。', 'それはとてもできません。'):
            self.assertEqual(run(s), s)

    def test_mixed_line_untouched(self):
        s = '資料をおくります'
        self.assertEqual(run(s), s)

    def test_switch_off(self):
        os.environ['CN_WAGO_VERB_KANJI'] = '0'
        try:
            self.assertEqual(run('ゆうはんをたべた'), 'ゆうはんをたべた')
        finally:
            del os.environ['CN_WAGO_VERB_KANJI']


if __name__ == '__main__':
    unittest.main()
