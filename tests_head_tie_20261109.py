# -*- coding: utf-8 -*-
"""head_tie: 既知の頭＋紫の2字の漢語を、1手の同点の候補を全部比べて直す（2026-11-09 手分けB）。例は作った文。"""
import os
import unittest
from unittest import mock

import head_tie as H
import vocabulary as V
from tests_analysis_async import initial

_ST = None


def _st():
    global _ST
    if _ST is None:
        _ST = initial()
    return _ST


def _res(line, spans):
    return {'original': line, 'corrected': line, 'changed': False, 'details': [], 'odd_spans': list(spans)}


_TIE = [('ちゅうりょく', 1.4, 1), ('にゅうりょく', 1.4, 1), ('ゆうりょく', 1.4, 2), ('きょうりょく', 2.4, 2)]


def _tie_flex(of):
    def f(r, *a, **k):
        return list(_TIE) if r == 'りゅうりょく' else of(r, *a, **k)
    return f


def _conv(of):
    # PC の語彙では ちゅうりょく も 注力 になる（雲の語彙には無い）
    def f(rd, *a, **k):
        return ('注力', 6) if rd == 'ちゅうりょく' else of(rd, *a, **k)
    return f


class HeadTie(unittest.TestCase):
    def run_line(self, line, spans):
        st = _st()
        return H.repair_line(line, _res(line, spans), st.store, st.dict_index)

    def test_tie_first_does_not_pair(self):
        # 同点の先頭（注力）は頭と組まず、2番（入力）だけが組む → 入力
        import corrector as C
        with mock.patch.object(V, 'find_known_readings_flex', _tie_flex(V.find_known_readings_flex)), \
                mock.patch.object(C, '_convert_odd_kana_run', _conv(C._convert_odd_kana_run)):
            out = self.run_line('一括流力', [(2, 4)])
        self.assertEqual(out['corrected'], '一括入力')
        self.assertEqual(out['odd_spans'], [])

    def test_two_pass_stays_purple(self):
        # 同点の2つがどちらも門を通れば決めない
        import semantic_roles
        import corrector as C
        with mock.patch.object(V, 'find_known_readings_flex', _tie_flex(V.find_known_readings_flex)), \
                mock.patch.object(C, '_convert_odd_kana_run', _conv(C._convert_odd_kana_run)), \
                mock.patch.object(semantic_roles, 'nominal_compound_support', lambda a, b: True):
            out = self.run_line('一括流力', [(2, 4)])
        self.assertEqual(out['corrected'], '一括流力')
        self.assertEqual(out['odd_spans'], [(2, 4)])

    def test_no_purple(self):
        out = self.run_line('一括流力', [])
        self.assertEqual(out['corrected'], '一括流力')

    def test_switch(self):
        os.environ['CN_HEAD_TIE'] = '0'
        try:
            out = self.run_line('一括流力', [(2, 4)])
        finally:
            del os.environ['CN_HEAD_TIE']
        self.assertEqual(out['corrected'], '一括流力')


if __name__ == '__main__':
    unittest.main()
