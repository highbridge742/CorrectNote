# -*- coding: utf-8 -*-
"""split_merge: 組にした表記は打った読みのとおりに読まれる物だけ候補にする（2026-11-09 手分けA）。
例は作った読み。py tests_split_merge_readback_20261109.py"""
import os
import split_merge as SM


def test_readback():
    os.environ.pop('CN_SPLIT_MERGE_READBACK', None)
    assert '巨大化' in SM.faces('きょだいか')
    assert '出家' not in SM.faces('いでいえ')       # 出 を いで と読む組は IME が返さない


def test_switch_off():
    os.environ['CN_SPLIT_MERGE_READBACK'] = '0'
    try:
        assert '出家' in SM.faces('いでいえ')
    finally:
        os.environ.pop('CN_SPLIT_MERGE_READBACK', None)


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
