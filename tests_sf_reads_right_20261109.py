# -*- coding: utf-8 -*-
"""semantic_fit: 元の表記で正しく読める所は替えない（2026-11-09 手分けA）。例は作った文。
py tests_sf_reads_right_20261109.py"""
import os
import semantic_fit as SF


def _fixes(text):
    return [m[2] for m in SF.propose(text)]


def test_one_char_noun_keeps_verb():
    assert _fixes('本棚の間を空けておく') == []          # 1字の名詞は重み比べで動詞を替えない


def test_time_suffix_keeps_noun():
    assert _fixes('機械の操作中は手を離さない') == []   # サ変の名詞＋中 はそのまま読める


def test_still_fixes():
    assert _fixes('選択物を外に干す') == ['洗濯物']     # 一般の接尾（物）は前のまま
    assert _fixes('私用量を減らす') == ['使用量']
    assert _fixes('文字を描く') == ['書く']             # 2字の名詞の重み比べは前のまま


def test_switches_off():
    os.environ['CN_SF_FIT_OUTWEIGH_ONE'] = '0'
    os.environ['CN_SF_COMPOUND_TIME_SUFFIX'] = '0'
    try:
        assert _fixes('本棚の間を空けておく') == ['開け']
        assert _fixes('機械の操作中は手を離さない') == ['捜査中']
    finally:
        os.environ.pop('CN_SF_FIT_OUTWEIGH_ONE', None)
        os.environ.pop('CN_SF_COMPOUND_TIME_SUFFIX', None)


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
