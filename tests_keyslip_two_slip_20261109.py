# -*- coding: utf-8 -*-
"""keyslip_window: 2打の戻しの動詞（巻き込み1打＋゛の抜け1打）と、が・を・に・行の頭の後ろの の（2026-11-09 手分けB）。
例は作った文。打った記録は無い（辞書の読み）。"""
import os
import unittest

import kanji_guess
import keyslip_window as K


def _p(line):
    kanji_guess.set_ime_readings_provider(lambda s: [])
    try:
        return K.propose(line)
    finally:
        kanji_guess.set_ime_readings_provider(lambda s: [])


def _fixed(line, marks):
    out = line
    for s, e, face, _src in sorted(marks, reverse=True):
        if face:
            out = out[:s] + face + out[e:]
    return out


class TwoSlipVerb(unittest.TestCase):
    def test_variants(self):
        # は の隣の き の巻き込み＋し の ゛ の抜け
        self.assertIn('はじめる', K._two_slip_variants('はきしめる'))
        self.assertIn('はじめる', K._two_slip_variants('はひしめる'))
        self.assertFalse(any('゛' in v for v in K._two_slip_variants('はきしめる')))

    def test_fix(self):
        self.assertEqual(_fixed('練習を破棄締める', _p('練習を破棄締める')), '練習を始める')
        self.assertEqual(_fixed('練習を歯日占める', _p('練習を歯日占める')), '練習を始める')

    def test_dropped_particle_kept(self):
        for line in ('練習頑張る', '会議始める', '仕事探している', '部屋片付ける'):
            self.assertEqual(_p(line), [], line)

    def test_switch(self):
        os.environ['CN_KEYSLIP_TWO_SLIP'] = '0'
        try:
            self.assertNotEqual(_fixed('練習を破棄締める', _p('練習を破棄締める')), '練習を始める')
        finally:
            del os.environ['CN_KEYSLIP_TWO_SLIP']


class StackedNo(unittest.TestCase):
    def test_fix(self):
        self.assertEqual(_fixed('荷物がの日っています', _p('荷物がの日っています')), '荷物が残っています')

    def test_added_no_dropped(self):
        # 助詞の後ろに足された の（1字の語）は抜く。の→に の戻しで助詞を重ねない（にに）
        line = '契約の内容にのついて担当者に相談した'
        self.assertEqual(_fixed(line, _p(line)), '契約の内容について担当者に相談した')

    def test_correct_kept(self):
        for line in ('の話を聞いた', '駅からの道', '田中がの部分を直した', '本をのせておく'):
            self.assertEqual(_fixed(line, _p(line)), line, line)

    def test_switch(self):
        os.environ['CN_KEYSLIP_STACKED_NO'] = '0'
        try:
            self.assertEqual(_p('荷物がの日っています'), [])
        finally:
            del os.environ['CN_KEYSLIP_STACKED_NO']


if __name__ == '__main__':
    unittest.main()
