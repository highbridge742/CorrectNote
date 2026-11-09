# -*- coding: utf-8 -*-
"""keyslip_window: かなだけの行でも、前の段が紫にした所のひらがなの並びの巻き込みを見る（ODD_HIRA_KANA）。
correction_entry._swap_rival_rarer: 入れ替えの形の語がずっと珍しいなら張り合わない（2026-11-09 手分けB）。例は作った文。"""
import os
import unittest

import kanji_guess
import keyslip_window as K


def _p(line, odd):
    kanji_guess.set_ime_readings_provider(lambda s: [])
    return [tuple(m[:3]) for m in K.propose(line, odd=odd)]


class OddHiraKana(unittest.TestCase):
    def test_kana_line_purple_spot(self):
        # かいせき の い の隣の す の巻き込み（紫は前の段が せき に付けた）
        self.assertEqual(_p('かいすせきがおわった', [(3, 5)]), [(0, 5, '解析')])

    def test_no_purple_no_window(self):
        self.assertEqual(_p('かいすせきがおわった', []), [])

    def test_switch(self):
        os.environ['CN_KEYSLIP_ODD_HIRA_KANA'] = '0'
        try:
            self.assertEqual(_p('かいすせきがおわった', [(3, 5)]), [])
        finally:
            del os.environ['CN_KEYSLIP_ODD_HIRA_KANA']


class SwapRivalRarer(unittest.TestCase):
    def test_rarer_rival(self):
        import correction_entry as CE
        from morphology import path_cost
        done, cand = 'いれました', 'いのれました'
        self.assertTrue(CE._swap_rival_rarer(done, cand, path_cost(done), path_cost(cand)))
        os.environ['CN_SWAP_RIVAL_RANK'] = '0'
        try:
            self.assertFalse(CE._swap_rival_rarer(done, cand, path_cost(done), path_cost(cand)))
        finally:
            del os.environ['CN_SWAP_RIVAL_RANK']


if __name__ == '__main__':
    unittest.main()
