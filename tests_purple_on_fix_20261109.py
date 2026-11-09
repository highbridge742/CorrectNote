# -*- coding: utf-8 -*-
"""correction_entry._keep_sahen_passive（〜せられる は正しい受け身）と _purple_on_fix（直した字の上に紫が残る
直しは戻して紫だけ）。2026-11-09 手分けB。例は作った文。"""
import os
import unittest

import correction_entry as CE


def _r(line, fixed, odd=()):
    return {'original': line, 'corrected': fixed, 'changed': fixed != line,
            'details': [] if fixed == line else [(line, fixed, 'かな入力')], 'odd_spans': list(odd), 'odd_reasons': []}


class SahenPassive(unittest.TestCase):
    def test_revert_fix(self):
        out = CE._keep_sahen_passive('課せられた義務', _r('課せられた義務', '変わられた義務'))
        self.assertEqual(out['corrected'], '課せられた義務')
        self.assertEqual(out['odd_spans'], [])

    def test_drop_purple(self):
        out = CE._keep_sahen_passive('税を課せられた', _r('税を課せられた', '税を課せられた', [(2, 6)]))
        self.assertEqual(out['odd_spans'], [])

    def test_other_fix_kept(self):
        # 対の外の直しはそのまま
        out = CE._keep_sahen_passive('課せられた義無', _r('課せられた義無', '課せられた義務'))
        self.assertEqual(out['corrected'], '課せられた義務')

    def test_switch(self):
        os.environ['CN_KEEP_SAHEN_PASSIVE'] = '0'
        try:
            out = CE._keep_sahen_passive('課せられた', _r('課せられた', '変わられた'))
        finally:
            del os.environ['CN_KEEP_SAHEN_PASSIVE']
        self.assertEqual(out['corrected'], '変わられた')


class PurpleOnFix(unittest.TestCase):
    def test_revert_under_purple(self):
        line = 'きとゅうか(例)'
        out = CE._purple_on_fix(line, _r(line, 'と中下(例)', [(0, 5)]))
        self.assertEqual(out['corrected'], line)
        self.assertEqual(out['odd_spans'], [(0, 5)])

    def test_fix_without_purple_kept(self):
        line = 'きとゅうか(例)'
        out = CE._purple_on_fix(line, _r(line, 'と中下(例)', []))
        self.assertEqual(out['corrected'], 'と中下(例)')

    def test_other_purple_mapped(self):
        # 直しの外の紫は、直しが残れば直した行の位置のまま
        line = 'あいう変所'
        out = CE._purple_on_fix(line, _r(line, 'あいう返事', [(0, 1)]))
        self.assertEqual(out['corrected'], 'あいう返事')
        self.assertEqual(out['odd_spans'], [(0, 1)])

    def test_switch(self):
        os.environ['CN_PURPLE_ON_FIX'] = '0'
        try:
            line = 'きとゅうか(例)'
            out = CE._purple_on_fix(line, _r(line, 'と中下(例)', [(0, 5)]))
        finally:
            del os.environ['CN_PURPLE_ON_FIX']
        self.assertEqual(out['corrected'], 'と中下(例)')


if __name__ == '__main__':
    unittest.main()
