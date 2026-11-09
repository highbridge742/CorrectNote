# -*- coding: utf-8 -*-
"""かなの行の 漢字1字の漢語＋する（察して）と、を・が の前の名詞（意図）を漢字に置く（2026-11-08 手分けA）。例は作った文。
2つ目と3つ目のクラスは kana_keep・kana_lattice_place の案を入れたときだけ通る。"""
import os
import unittest

import kana_piece_word as K


class SahenMarks(unittest.TestCase):
    def test_kango_sahen(self):
        self.assertEqual(K._sahen_marks('きもちをさっした。'), [(4, 7, '察し')])
        self.assertEqual(K._sahen_marks('ふゆにてきしている'), [(3, 6, '適し')])

    def test_wago_and_ambiguous_untouched(self):
        self.assertEqual(K._sahen_marks('でんきをけしてください'), [])      # 消す（和語）
        self.assertEqual(K._sahen_marks('それにかんしては'), [])           # 関し／冠し
        self.assertEqual(K._sahen_marks('つたえることがあります'), [])
        self.assertEqual(K._sahen_marks('ほんをさがしている'), [])

    def test_switch(self):
        os.environ['CN_KANA_PIECE_SAHEN'] = '0'
        try:
            self.assertEqual(K._sahen_marks('きもちをさっした。'), [])
        finally:
            del os.environ['CN_KANA_PIECE_SAHEN']


class KanaKeepSahen(unittest.TestCase):
    def test_is_kango_sahen(self):
        import kana_keep as KK
        self.assertTrue(KK.is_kango_sahen('察し', 'さっし'))
        self.assertTrue(KK.is_kango_sahen('適し', 'てきし'))
        self.assertFalse(KK.is_kango_sahen('消し', 'けし'))
        self.assertFalse(KK.is_kango_sahen('話し', 'はなし'))


class CasePairFace(unittest.TestCase):
    def test_tatoeba_pair(self):
        import kana_lattice_place as L
        self.assertTrue(L._tatoeba_pair('を', '意図', '察す'))
        self.assertFalse(L._tatoeba_pair('を', '糸', '察す'))


if __name__ == '__main__':
    unittest.main()
