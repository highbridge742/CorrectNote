# -*- coding: utf-8 -*-
"""前後とも語から離れたかな1字（字そのものを書いたメモ）に、品詞のつながりの紫を付けない（2026-11-09 手分けA）。
例は作った文。py tests_lone_kana_mention_20261109.py"""
import os
from pos_grammar import _impossible_connection_spans as spans


def test_mention_in_memo():
    os.environ.pop('CN_POS_ODD_LONE_MENTION', None)
    assert spans('メモ(ゅ と と の順が逆)') == ()
    assert spans('メモ（ょ と よ の取り違え）') == ()


def test_fragment_still_marked():
    os.environ.pop('CN_POS_ODD_LONE_MENTION', None)
    assert spans('にぱ家族') == ((1, 2),)      # 語に付いた切れ端は前のまま紫


def test_switch_off():
    os.environ['CN_POS_ODD_LONE_MENTION'] = '0'
    try:
        assert spans('メモ(ゅ と と の順が逆)') == ((3, 4),)
    finally:
        os.environ.pop('CN_POS_ODD_LONE_MENTION', None)


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
