# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# ---------------------------------------------------------------
# このファイルが読む `familiarity.json` は UniDic から導いたもの。
#   Derived from UniDic.
#   Copyright (c) 2011-2017, The UniDic Consortium.
#   All rights reserved. (modified BSD License)
# **表を作り直しても、この表示は必ず残すこと**（修正BSDの条件）。
# ---------------------------------------------------------------

"""
**馴染みの薄い語の優先を下げる**（うにさんの指定・2026-08-11）。

「馴染みの言葉、自然な言葉は個人にとってのものではなく、**世界の
基準**で判断することになります。しかしそれは**新聞が基準では
ありません**。（略）**書籍の中から基準が見つかるとよい**ですね」

**いまの基準は新聞だった。** janome 同梱の IPAdic は毎日新聞の
コーパスで学習されているので、`良い` のような新聞頻出語が
**-1567**（負の値）まで安くなる。そのせいで
`安全性 → 安全良い` のような置き換えが「自然になった」と
判定されていた（項目48-AE の穴2）。

**書籍を含む基準に寄せる。** UniDic は BCCWJ（書籍を柱に
雑誌・新聞・白書・ブログ等をジャンル横断で集めた現代語コーパス。
古典は入らない）で学習されている。同じ `良い` が **4228**。

同梱はしない（辞書だけで250MB）。語ごとの**ずれ**

    ずれ(語) = UniDic のコスト − IPAdic のコスト（正のぶんだけ）

を `familiarity.json`（13716語・257KB）に持ち、
経路コストに足す。**正なら「新聞基準では安すぎる語」＝馴染みが薄い**。

表の作り方は `familiarity_build.py`（開発時のみ。実機には
MeCab も UniDic も要らない）。

実測（22組で、通したい／止めたいが合っているか）:

    ずれを使わない  14/22  →  ずれを足す  **17/22**
"""

import json
import os

# ずれをどれだけ効かせるか。
# **実測で決めた**（familiarity_build.py の説明）。
#   0.0 → 14/22 ／ 0.5 → 16/22 ／ **1.0 → 17/22** ／
#   1.5 → 17/22 ／ 2.0 → 15/22（効かせすぎ。正しい直しまで落ちる）
# 2.0 では `性格→正確` `野外文章→長い文章` が通らなくなる。
WEIGHT = 1.0

# 1文字の語は見ない。ずれが大きく出やすいわりに、
# 経路コスト側（前後の繋がり）のほうが確かなため。
MIN_LEN = 2

_TABLE = None
_MISSING = False


def _load():
    global _TABLE, _MISSING
    if _TABLE is not None or _MISSING:
        return _TABLE
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'familiarity.json'),
                 'familiarity.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            got = data.get('bias')
            if isinstance(got, dict):
                _TABLE = got
                return _TABLE
        except Exception:
            continue
    # **無くても動く**。表が無ければ「ずれ0」＝今までどおり。
    _MISSING = True
    return None


def available():
    """表が読めているか（診断用）。"""
    return _load() is not None


def bias(word):
    """
    その語の**馴染みの薄さ**（0以上。大きいほど馴染みが薄い）。

    表に無ければ 0（＝下げない）。**知らない語を勝手に下げない**。
    表に載っているのはこのアプリが提案しうる語だけなので、
    「載っていない＝提案しない語」であり、下げる意味が無い。
    """
    if not word or len(word) < MIN_LEN:
        return 0
    table = _load()
    if not table:
        return 0
    return table.get(word, 0)


def penalty(words):
    """語の並びぶんの、馴染みの薄さの合計（重み込み）。"""
    table = _load()
    if not table:
        return 0
    total = 0
    for w in words or ():
        if w and len(w) >= MIN_LEN:
            total += table.get(w, 0)
    return int(WEIGHT * total)
