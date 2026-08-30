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
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
**読みの並びの統計**（2026-08-28・項目48-KJ の続き）。

うにさんの指定（2026-08-28）:

> 「本アプリ上で文字を打てば、変換前のひらがなの文字列情報が取れて
>   いるので、その文字並びと、言語特徴の一致率から怪しい個所を出す
>   方向です。**次に来やすいキーは、各種補正よりも先に見てください。**
>   前の1文字を見て、その文字の次に来やすい文字の上位を出し、上位の
>   中に8つの隣接キーがあれば優先してピックアップできます。可能で
>   あれば**前の2文字の流れから、2文字を元にした3文字目に来やすい
>   1文字まで**できると精度が高いです。文頭であれば文頭で多い文字を
>   優先。文末もそうです」

表は `ngram_yomi.py`（**読み**の文字3連。表記の3連 `ngram_ja.py` は
かなの読みには効かない——項目48-KJ で実測）。`^^` が頭・`$` が尾の
印なので、**文頭・文末の統計も同じ表から読める**。

`charngram`（表記の3連・止める側）とは持ち場が違う:

    charngram   表記の並びが日本語として無理か（出口の検品・止める側）
    yomigram    **読みの並びのどこが怪しいか・次に何が来やすいか**
                （①異様の材料と、③④の候補の優先順位）

いまは**同梱の表だけ**（初期状態を重要視——うにさんの指定）。
育ちはまだ持たない。育てるなら charngram と同じ形（直すところが
無かった行の読みを数える・ENGINE の指紋に足す）にすること。
"""

import math

_TABLE = None       # 3連 → 回数
_CTX2 = None        # 2連（文脈）→ 回数
_NEXT = None        # 2連（文脈）→ [(次の字, 回数), …] 回数順
_MISSING = False

# 見たことのない文字の種類ぶんの重み（スムージングの分母）。
# 読みの字はかな＋ー で約90種。倍を見て 200。
_VOCAB = 200
_FLOOR = 0.1


def _load():
    global _TABLE, _CTX2, _NEXT, _MISSING
    if _TABLE is not None or _MISSING:
        return _TABLE
    try:
        import ngram_yomi
        _TABLE = ngram_yomi.TRIGRAMS
    except Exception:
        _MISSING = True
        return None
    ctx = {}
    nxt = {}
    for g, c in _TABLE.items():
        k = g[:2]
        ctx[k] = ctx.get(k, 0) + c
        nxt.setdefault(k, []).append((g[2], c))
    for k in nxt:
        nxt[k].sort(key=lambda t: (-t[1], t[0]))
    _CTX2, _NEXT = ctx, nxt
    return _TABLE


def available():
    return _load() is not None


def logp_parts(text):
    """合計の対数確率と3連の数 `(total, n)`。表が無ければ (0.0, 0)。"""
    table = _load()
    if not table or not text:
        return (0.0, 0)
    s = '^^' + text + '$'
    total = 0.0
    n = 0
    for i in range(len(s) - 2):
        g = s[i:i + 3]
        total += math.log((table.get(g, 0) + _FLOOR)
                          / (_CTX2.get(g[:2], 0) + _FLOOR * _VOCAB))
        n += 1
    return (total, n)


def score(text):
    """1文字あたりの対数確率（0に近いほど読みの並びらしい）。"""
    total, n = logp_parts(text)
    return total / max(1, n)


def next_ranking(prev2):
    """
    **2文字の文脈から、3文字目に来やすい字の順**（うにさんの指定の形）。

    prev2: 直前の2文字。連続の頭は `'^^'`、2文字目なら `'^' + 1文字目`。
    戻り値: [(字, 回数), …] 回数の多い順。文脈が表に無ければ、
    **前の1文字だけの文脈**（prev2[1] で始まる3連の足し上げ）に落とす。
    それも無ければ []。
    """
    if _load() is None or not prev2 or len(prev2) != 2:
        return []
    got = _NEXT.get(prev2)
    if got:
        return got
    # 1文字の文脈に落とす（前の1文字を見て、の側）
    one = prev2[1]
    agg = {}
    for k, items in _NEXT.items():
        if k[1] != one:
            continue
        for ch, c in items:
            agg[ch] = agg.get(ch, 0) + c
    return sorted(agg.items(), key=lambda t: (-t[1], t[0]))


def trigram_count(prev2, ch):
    """文脈 prev2 のあとに ch が来た回数（無ければ0）。"""
    table = _load()
    if not table or len(prev2) != 2:
        return 0
    return table.get(prev2 + ch, 0)


def position_surprise(run):
    """
    **読みの連続の、位置ごとの意外さ**（怪しい箇所を出す材料）。

    戻り値: run と同じ長さの一覧。各位置の値は「その字を含む3連の
    対数確率の平均」（小さいほど怪しい）。表が無ければ []。
    """
    table = _load()
    if not table or not run:
        return []
    s = '^^' + run + '$'
    lp = []
    for i in range(len(s) - 2):
        g = s[i:i + 3]
        lp.append(math.log((table.get(g, 0) + _FLOOR)
                           / (_CTX2.get(g[:2], 0) + _FLOOR * _VOCAB)))
    out = []
    for pos in range(len(run)):
        # run[pos] は s の pos+2 文字目。関わる3連は
        # lp[pos]（末尾が run[pos]）・lp[pos+1]（真ん中）・lp[pos+2]（先頭）
        vals = [lp[k] for k in (pos, pos + 1, pos + 2) if 0 <= k < len(lp)]
        out.append(sum(vals) / max(1, len(vals)))
    return out


def stats():
    """診断用: (3連の種類, 文脈の種類)"""
    if _load() is None:
        return (0, 0)
    return (len(_TABLE), len(_CTX2))
