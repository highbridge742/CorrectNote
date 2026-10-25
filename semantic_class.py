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
**語の意味の分類**で、語の組（collocation_table）を表に書いていない名詞へ広げる（2026-10-24）。

分類は国立国語研究所『分類語彙表増補改訂版データベース』の「体」の類。表 wlsp_nouns.json.gz は
見出し → [読み, [分類番号…]]（1.3122 = 体・活動・言語・通信）。データは CC BY-NC-SA 3.0
（表示・非営利・継承）で、ライセンスの文と出典は表の "license"・"source" に入っている。

組の表の (助詞, 述語) ごとに、表の名詞の分類番号を集めて「その組の意味の仲間」とする
（を＋飲む → 1.4350 飲料）。collocation_repair はここに3つだけ聞く:
- fits: 元の名詞が身近な語で組の仲間か（元の組も言える）
- candidates: 表の名詞に届かないとき、1打隣か同じ読みの、組の仲間の身近な語
- foreign: 元の名詞が分類に在って組の仲間でないか（中項目で広く比べる）→ 組の語が1打隣に在れば紫
表が読めないとき（ファイルが無い等）はどれも「何も言わない」答えを返し、collocation_repair はいまと同じ答えになる。
本人の書いた文からは学ばない。
"""

from cache_limits import size as _cache_size   # 控えの上限は cache_limits で1か所に（2026-10-24）
import os
from functools import lru_cache

# 元の名詞の仲間は中項目（1.31 言語）で広く比べる。候補は分類項目（1.3122 通信）で狭く比べる
FOREIGN_DEPTH = 4


@lru_cache(maxsize=1)
def _data():
    import gzip
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wlsp_nouns.json.gz')
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            words = json.load(f)['words']
    except Exception:
        words = {}
    by_reading = {}
    for face, (read, _codes) in words.items():
        by_reading.setdefault(read, []).append(face)
    return words, by_reading


def available():
    return bool(_data()[0])


def codes(word):
    """語の分類番号の組（無ければ空）。"""
    e = _data()[0].get(word)
    return frozenset(e[1]) if e else frozenset()


def words_read(reading):
    """その読みの見出しの並び。"""
    return tuple(_data()[1].get(reading, ()))


def _table_nouns(p, v):
    from collocation_repair import table
    return table()[1].get((p, v), ())


@lru_cache(maxsize=_cache_size(1024))
def pv_classes(p, v):
    """(助詞, 述語) と組になる名詞の分類番号（表の名詞の番号の集まり）。"""
    out = set()
    for n in _table_nouns(p, v):
        out |= codes(n)
    return frozenset(out)


def _shares(noun, p, v, depth=None):
    mine, theirs = codes(noun), pv_classes(p, v)
    if depth:
        mine, theirs = {c[:depth] for c in mine}, {c[:depth] for c in theirs}
    return bool(mine & theirs)


def fits(noun, p, v, familiar):
    """身近な語で、表の名詞と同じ分類番号なら、元の組も言える。"""
    return familiar(noun) and _shares(noun, p, v)


def foreign(noun, p, v):
    """分類語彙表に在って、組の意味の仲間でない（中項目でも重ならない）名詞。"""
    return bool(codes(noun)) and not _shares(noun, p, v, FOREIGN_DEPTH)


def strong(cand, p, v):
    """その仲間が表の名詞の2語以上に出ているか。1語だけなら、仲間とみなす根拠が弱いので紫だけにする。"""
    mine = codes(cand)
    return max((sum(1 for n in _table_nouns(p, v) if c in codes(n)) for c in mine), default=0) >= 2


def candidates(p, v, readings, familiar):
    """読み（同じ・1打隣）が届く、表の名詞と同じ分類番号の、漢字を含む身近な語（層1）。"""
    cls = pv_classes(p, v)
    out = set()
    for r in readings:
        for w in words_read(r):
            if codes(w) & cls and any('一' <= c <= '鿿' or c == '々' for c in w) and familiar(w):
                out.add(w)
    return out
