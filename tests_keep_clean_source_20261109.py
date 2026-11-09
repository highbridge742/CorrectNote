# -*- coding: utf-8 -*-
"""correction_entry._keep_clean_source: 元の行に異様な並びが無いのに、入口の直しで異様な並びが立つなら戻す
（2026-11-09 手分けB）。例は作った文。"""
import os
import unittest

import correction_entry as CE
from tests_analysis_async import initial

_ST = None


def _st():
    global _ST
    if _ST is None:
        _ST = initial()
    return _ST


def _r(line, fixed):
    return {'original': line, 'corrected': fixed, 'changed': fixed != line,
            'details': [(line, fixed, 'x')] if fixed != line else [], 'odd_spans': [], 'odd_reasons': []}


class KeepCleanSource(unittest.TestCase):
    def run_it(self, line, fixed):
        st = _st()
        return CE._keep_clean_source(line, _r(line, fixed), st.store, st.dict_index)

    def test_revert_broken(self):
        out = self.run_it('ボタンをクリックして選べる3つの色', 'ボタンをクリック下よべる3つの色')
        self.assertEqual(out['corrected'], 'ボタンをクリックして選べる3つの色')

    def test_keep_clean_fix(self):
        # 直した形に異様な並びが無ければそのまま
        out = self.run_it('ボタンをクリックして選べる3つの色', 'ボタンをクリックが呼べる3つの色')
        self.assertEqual(out['corrected'], 'ボタンをクリックが呼べる3つの色')

    def test_odd_source_kept(self):
        # 元の行に異様な並びが在れば（打ち違いの行）、入口の直しはそのまま
        out = self.run_it('ボタンをクリック下よべる3つの色', 'ボタンをクリックして選べる3つの色')
        self.assertEqual(out['corrected'], 'ボタンをクリックして選べる3つの色')

    def test_switch(self):
        os.environ['CN_KEEP_CLEAN_SOURCE'] = '0'
        try:
            out = self.run_it('ボタンをクリックして選べる3つの色', 'ボタンをクリック下よべる3つの色')
        finally:
            del os.environ['CN_KEEP_CLEAN_SOURCE']
        self.assertEqual(out['corrected'], 'ボタンをクリック下よべる3つの色')


if __name__ == '__main__':
    unittest.main()
