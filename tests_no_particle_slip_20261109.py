# -*- coding: utf-8 -*-
"""副助詞＋の＋用言 の の を隣のキーの格助詞として見る（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import no_particle_slip as N


class NoParticleSlip(unittest.TestCase):
    def test_kana(self):
        self.assertEqual(N.propose('えきまでのいった', 'kana'), [(4, 5, 'に')])

    def test_romaji(self):
        self.assertEqual(N.propose('えきまでのいった', 'romaji'), [(4, 5, 'に')])

    def test_noun_after(self):
        self.assertEqual(N.propose('本などの棚', 'kana'), [])

    def test_switch(self):
        os.environ['CN_NO_PARTICLE_SLIP'] = '0'
        try:
            res = {'original': 'えきまでのいった', 'corrected': 'えきまでのいった', 'odd_spans': []}
            self.assertIs(N.repair_line('えきまでのいった', res), res)
        finally:
            del os.environ['CN_NO_PARTICLE_SLIP']


if __name__ == '__main__':
    unittest.main()
