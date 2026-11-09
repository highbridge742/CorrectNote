# -*- coding: utf-8 -*-
"""keyslip_window._split_particle: 1字ずつに切れたひらがなの並びの中の1字の助詞（せ｜つ｜さ｜めい の さ）は、
紫の所の窓を広げ、足された1打として抜いてよい（2026-11-09 手分けB）。かな入力だけ。例は作った文。"""
import os
import unittest

import kanji_guess
import keyslip_window as K


def _p(line, odd):
    kanji_guess.set_ime_readings_provider(lambda s: [])
    return [tuple(m[:3]) for m in K.propose(line, odd=odd)]


class SplitParticle(unittest.TestCase):
    def test_roll_in_inside_split_run(self):
        # つ の隣の さ の巻き込み（紫は前の段が めい に付けた）
        self.assertEqual(_p('せつさめいをよむ', [(3, 5)]), [(0, 5, '説明')])

    def test_no_purple_no_window(self):
        self.assertEqual(_p('せつさめいをよむ', []), [])

    def test_real_particle_kept(self):
        # 前が1字に切れていない助詞はそのまま（窓を広げない）
        self.assertEqual(_p('にわでさくらがさく', []), [])

    def test_switch(self):
        os.environ['CN_KEYSLIP_SPLIT_PARTICLE'] = '0'
        try:
            self.assertEqual(_p('せつさめいをよむ', [(3, 5)]), [])
        finally:
            del os.environ['CN_KEYSLIP_SPLIT_PARTICLE']


if __name__ == '__main__':
    unittest.main()
