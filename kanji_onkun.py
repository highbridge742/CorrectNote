# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ---------------------------------------------------------------
# このファイルが読む `kanji_onkun.json` は UniDic から導いたもの。
#   Derived from UniDic.
#   Copyright (c) 2011-2017, The UniDic Consortium.
#   All rights reserved. (modified BSD License)
# **表を作り直しても、この表示は必ず残すこと**（修正BSDの条件）。
# ---------------------------------------------------------------

"""
**単漢字の読み（音読み・訓読みの印つき）**。

うにさんの指定（2026-08-11）:

「**音読みと訓読みの情報はありませんか？** IMEがどう変換するかを
考えたらよいです。あやまがくしゅうという文字列で変換したら、
別の文字列になります」

**なぜ要るか（実測で分かった穴）**:

    うにさんのメモに出る漢字 632種のうち、
    **284種（44%）は読みが1つも引けなかった**。

`格` `賀` もそこに入っていた。だから

    reading_combos_with_rank('性格') → **候補ゼロ**
    reading_combos_with_rank('賀古') → **候補ゼロ**

で、`性格→正確` `賀古→過去` はそもそも土俵に上がれていなかった。
「関門で止まっている」と思っていたが、**読みが無かった**。

**印は何に使うか**（うにさんの筋道）:

誤変換の文字列は、IMEが**読みから変換した結果**。だから
元の読みは「変換前に打った、ごく普通の読み」であって、
**熟語なら音読みどうし・和語なら訓読みどうし**で揃うのが普通。
`誤学習` は 誤(ご・音)＋学習(音) で **ごがくしゅう**。
janome は 誤 を **あやま**（訓）と読んで
`あやまがくしゅう` にしていた。うにさんの言うとおり、
**その読みでIMEに打っても `誤学習` は出てこない**。

ただし**揃わない語もある**（重箱読み・湯桶読み）。実測で
`待ち外`（＝間違いの誤変換）は **まち(訓)＋がい(音)** だった。
だから印は**順位づけの材料**であって、門にはしない。

    'on'  音読み（UniDic の語種が「漢」）
    'kun' 訓読み（同「和」）
    'gai' 外来語 ／ 'na' 固有名 ／ 'mix' 混種
    '?'   熟語からの引き算で足したもの（印は分からない）

表が無くても動く（今までどおりの読みだけになる）。
表の作り方は `kanji_onkun_build.py`（開発時のみ）。
"""

import json
import os

_TABLE = None
_MISSING = False


def _load():
    global _TABLE, _MISSING
    if _TABLE is not None or _MISSING:
        return _TABLE
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'kanji_onkun.json'),
                 'kanji_onkun.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            got = data.get('readings')
            if isinstance(got, dict):
                _TABLE = got
                return _TABLE
        except Exception:
            continue
    _MISSING = True
    return None


def available():
    """表が読めているか（診断用）。"""
    return _load() is not None


def readings_of(ch):
    """その漢字の読み（ひらがな）。**音読みを先に**並べて返す。

    誤変換のもとになる読みは、たいてい熟語の音読み。
    印の分からないもの（'?'）は最後に回す。
    """
    table = _load()
    if not table:
        return []
    got = table.get(ch)
    if not got:
        return []
    order = {'on': 0, 'kun': 1, 'gai': 2, 'mix': 3, 'na': 4, '?': 5}
    return [r for r, _k in sorted(got.items(),
                                  key=lambda x: order.get(x[1], 9))]


def kind_of(ch, reading):
    """その読みが音読みか訓読みか。分からなければ '?'。"""
    table = _load()
    if not table:
        return '?'
    return (table.get(ch) or {}).get(reading, '?')


def kinds_of_word(text, reading_per_char):
    """
    漢字ごとの読みの並びから、音訓の並びを返す（診断・順位づけ用）。

    reading_per_char: [(漢字, 読み), ...]
    """
    return [kind_of(c, r) for c, r in reading_per_char]


def mixed_reading(kinds):
    """
    音読みと訓読みが混ざっているか（重箱読み・湯桶読み）。

    **混ざっていること自体は誤りではない**（待ち外＝まち＋がい）。
    順位を下げる材料として使うだけで、門にはしないこと。
    """
    seen = {k for k in kinds if k in ('on', 'kun')}
    return len(seen) > 1
