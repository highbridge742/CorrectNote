# -*- coding: utf-8 -*-
"""keyslip_window._long_loan / long_loan_line: ひらがなの ー を含む外来語を片仮名に（かな入力の1キーの戻しも）、
correction_entry._loan_fix の前のかなを漢字にした直し（2026-11-09 手分けB）。例は作った文。記録なし。"""
import os
import unittest

import kanji_guess
import keyslip_window as K
from morphology import path_cost


def _ll(line, im='kana'):
    kanji_guess.set_ime_readings_provider(lambda s: [])
    return [tuple(m[:3]) for m in K._long_loan(line, path_cost(line), im)]


class LongLoan(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(_ll('学習めにゅー'), [(2, 6, 'メニュー')])
        self.assertEqual(_ll('がくしゅうめにゅー'), [(5, 9, 'メニュー')])

    def test_key_slip(self):
        # ゅ の隣の ょ
        self.assertEqual(_ll('学習めにょー'), [(2, 6, 'メニュー')])
        self.assertEqual(_ll('めにょーをひらく'), [(0, 4, 'メニュー')])

    def test_key_slip_romaji_not(self):
        self.assertEqual(_ll('学習めにょー', 'romaji'), [])

    def test_spoken_elongation_kept(self):
        for line in ('そーだね', 'すごーい', 'ごめーん', 'まーね', 'いいよー', 'じゃーね', 'もーいいよ'):
            self.assertEqual(_ll(line), [], line)

    def test_inside_longer_word_kept(self):
        # 外来語の途中で切らない・書いたままで外来語の所を打ち違いと見ない
        for line in ('ぼーるぺんで書く', 'せーるで買った', 'のーとぱそこんを開く'):
            self.assertEqual([m for m in _ll(line) if m[2] not in ('セール',)], [], line)

    def test_switch(self):
        os.environ['CN_KEYSLIP_LONG_LOAN'] = '0'
        try:
            res = {'original': '学習めにゅー', 'corrected': '学習めにゅー', 'changed': False}
            self.assertIs(K.long_loan_line('学習めにゅー', res), res)
        finally:
            del os.environ['CN_KEYSLIP_LONG_LOAN']


class LoanFixHead(unittest.TestCase):
    def test_head_kanji_same_reading(self):
        import correction_entry as CE
        import difflib
        line, done = 'がくしゅうめにょー', '学習メニュー'
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        self.assertTrue(CE._loan_fix(done, ops, line))
        os.environ['CN_ELONGATION_LOAN_HEAD'] = '0'
        try:
            self.assertFalse(CE._loan_fix(done, ops, line))
        finally:
            del os.environ['CN_ELONGATION_LOAN_HEAD']


if __name__ == '__main__':
    unittest.main()
