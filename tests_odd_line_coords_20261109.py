# -*- coding: utf-8 -*-
"""紫（odd_spans）を元の行の位置でそろえる（keyslip_window・correction_entry._revert_ops_map、2026-11-09 手分けA）。
例は作った文。py tests_odd_line_coords_20261109.py"""
import os
import keyslip_window as K


def test_map_span():
    line, done = 'きょうはにわの草をとる', '今日はにわの草をとる'
    # 直した行の にわ (3,5) は元の行の (4,6)
    assert K._map_span(done, line, 3, 5) == (4, 6)
    assert K._map_span(line, done, 4, 6) == (3, 5)
    # 変わった所は変わった範囲全体へ
    assert K._map_span(done, line, 0, 2) == (0, 3)
    assert K._map_span(line, line, 2, 4) == (2, 4)


def test_apply_purple_in_line_coords():
    os.environ.pop('CN_ODD_LINE_COORDS', None)
    line, done = 'きょうはにわの草をとる', '今日はにわの草をとる'
    res = {'original': line, 'corrected': done, 'changed': True, 'odd_spans': [(8, 9)], 'odd_reasons': []}
    out = K._apply(line, res, done, [(3, 5, '', 'にわ')])     # 直した行の にわ に紫
    assert (4, 6) in [tuple(x[:2]) for x in out['odd_spans']], out
    assert (8, 9) in [tuple(x[:2]) for x in out['odd_spans']], out   # 前からの紫は動かさない
    assert out['corrected'] == done


def test_apply_old_switch():
    os.environ['CN_ODD_LINE_COORDS'] = '0'
    try:
        line, done = 'きょうはにわの草をとる', '今日はにわの草をとる'
        res = {'original': line, 'corrected': done, 'changed': True, 'odd_spans': [], 'odd_reasons': []}
        out = K._apply(line, res, done, [(3, 5, '', 'にわ')])
        assert (3, 5) in [tuple(x[:2]) for x in out['odd_spans']], out
    finally:
        os.environ.pop('CN_ODD_LINE_COORDS', None)


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
