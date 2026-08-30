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
#
# ---------------------------------------------------------------
# このファイルが読む `seed_japanese.txt.gz` は SudachiDict から
# 作ったもの。
#   SudachiDict
#   Copyright (c) 2017-2026 Works Applications Co., Ltd.
#   Licensed under the Apache License, Version 2.0
#   http://www.apache.org/licenses/LICENSE-2.0
#   SudachiDict includes UniDic and a part of NEologd.
# **表を作り直しても、この表示は必ず残すこと**（Apache-2.0 の条件）。
# ---------------------------------------------------------------

"""
**その表記は「1語として在る」か**（項目48-FC）。

第44回で、うにさんの「文字列として違和感を感じるもの」を分ける
物差しを **11軸**測って、**同梱の材料はどれも分けませんでした**。
`殺意代価`（殺意＋代価）と `誤字補正`（誤字＋補正）は**形として
同じ**で、違いは「その語を人が使うか」＝**語の性質**だからです。

足りなかったのは判定の式ではなく**材料**でした。ここがその材料。

**絶対には使いません。**（`殺意代価` も `誤字補正` も「非単位」で、
そこは分かれません。第45回の実測。）**比べて使います**:

    元が1語として在る            → **触らない**
    元は非単位で、直し先が1語     → **疑わしい＝直してよい**

実測（第45回・15組）: **捨ててほしい組み直しの 14/15 が止まる**。
しかも第44回に「文字3連（項目48-EY）では止まらない」と書いた
2件が、これなら止まります:

    投機的 → 同期的   文字3連 +2.56（止まらない）→ **止まる**
    符号化 → 複合化   文字3連 +2.08（止まらない）→ **止まる**

**役割が違い、重なりません**:

    文字3連（同梱・0MB）  ゴミへの化けを止める（会派者・表時中）
    ここ（gzip 2.7MB）    もっともらしい別語への化けを止める

**二段に持ちます**（SCOWL の 35/70 と同じ・項目48-BU）:

    `is_unit`         触らない側（広い。固有名詞も入る。相川駅・兼六園）
    `is_common_unit`  直し先側（狭い。固有名詞は入らない）

広げすぎると「直したい誤字まで守ってしまう」ので、**直し先側には
固有名詞を入れません**（英語側で `accomodate` を入れて失敗した
のと同じ轍を踏まないため）。

> **実態の注意（2026-08-25・項目48-JE。測って分かった・Opus 2026-08-24）**:
> いまの `seed_japanese.txt.gz` は **778,340行が全部 `*` 付き**で、
> `*` 無しの行が0。つまり**広い側と狭い側はいま完全に同じ集合**で、
> 上の説明が言う「固有名詞も入る広い側」は**データに存在しない**
> （`相川駅` `兼六園` は**どちらの側にも無い**——実機でこれらが
> 守られているのは janome の辞書・解析の側）。関数の2つの口は
> 表が二段に戻ったときのために残す。**この説明だけを読んで
> 「固有名詞は表が守る」と思い込んで手当てを二重にしないこと**
> （48-ID の `_SCOPED_SUFFIX` は、この穴を塞いだ実例）。

表の作り方は `seed_japanese_build.py`（**開発時にネットへ1回だけ**。
実機はオフラインのままです）。**表が無くても動きます** ——
無ければ「意見なし」を返し、これまでどおりの判断になります。
"""

import gzip
import os

_WIDE = None        # 触らない側（固有名詞も入る）
_NARROW = None      # 直し先側（固有名詞は入らない）
_MISSING = False

FILENAME = 'seed_japanese.txt.gz'
MIN_LEN = 2


def _load():
    global _WIDE, _NARROW, _MISSING
    if _WIDE is not None or _MISSING:
        return _WIDE
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, FILENAME), FILENAME):
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                wide, narrow = set(), set()
                for raw in f:
                    s = raw.rstrip('\n')
                    if not s:
                        continue
                    if s[0] == '*':
                        s = s[1:]
                        narrow.add(s)
                    wide.add(s)
            if wide:
                _WIDE, _NARROW = wide, narrow
                return _WIDE
        except Exception:
            continue
    # **無くても動く**。表が無ければ「意見なし」＝今までどおり。
    _MISSING = True
    return None


def available():
    """表が読めているか（診断用）。"""
    return _load() is not None


def stats():
    """表の大きさ（診断用）。"""
    if _load() is None:
        return (0, 0)
    return (len(_WIDE or ()), len(_NARROW or ()))


def in_scope(surface):
    """
    **この表が意見を持てる形か**（項目48-FD）。

    表に入っているのは**日本語の文字だけの 2〜8字**の表記
    （ひらがな・カタカナ・漢字・々・ー）。英数字や記号が混じるものは
    **表に無いのではなく、そもそも範囲の外**。

    **最初は漢字だけだった**（項目48-FM）。そのせいで `メモ帳`・
    `ひらがな`・`指示し` に何も言えず、候補の並べ替えで
    `メモ帳` を落としかけた。うにさんの指摘で、かなを含む語も
    表に入れるようにした。

    **ここを見ないと「知らない」を「無い」と読み違える。**
    実際、候補の並べ替えで `目もち長` の答えである `メモ帳` を
    `無料` の下へ落としてしまった（2026-08-18 に実測して足した）。
    """
    if not surface or not (MIN_LEN <= len(surface) <= 8):
        return False
    return all('ぁ' <= c <= 'ゖ'          # ひらがな
               or 'ァ' <= c <= 'ヶ'       # カタカナ
               or c in 'ー々'
               or '一' <= c <= '鿿'       # 漢字
               for c in surface)


def is_unit(surface):
    """
    **その表記は、日本語で1語として在るか**（広い側）。

    在るなら「正しく書けている」とみなして**触らない**のに使う。
    固有名詞も入っている（`相川駅` `兼六園` を守るため）。

    表が無ければ **None**（＝意見なし。呼ぶ側は今までどおりに）。
    **False と None を混ぜないこと。** False は「無いと言い切れる」、
    None は「分からない」。
    """
    if not surface or len(surface) < MIN_LEN:
        return None
    if _load() is None:
        return None
    return surface in _WIDE


def is_common_unit(surface):
    """
    **その表記は、直し先にしてよい語か**（狭い側・固有名詞を除く）。

    「元は非単位なのに、直し先は1語」＝**疑わしい**の判定に使う。
    珍しい地名・人名へ引っぱられないよう、固有名詞は入れていない。

    表が無ければ **None**（＝意見なし）。
    """
    if not surface or len(surface) < MIN_LEN:
        return None
    if _load() is None:
        return None
    return surface in (_NARROW or ())


def rebuild_is_suspicious(before, after):
    """
    **その組み直しは疑わしいか**（比べる形・項目48-FC）。

    うにさんの指示 (h)「ネット検索のヒット数のような一般性の
    物差しが、オフラインで要る」への答え。**絶対には使わず、
    元と直し先を比べます**:

        元が1語として在る          → **False**（触らない）
        元は非単位で、直し先が1語   → **True**（直してよい）
        それ以外                   → **None**（意見なし）

    None のときは、呼ぶ側がこれまでの門で決めること。
    **「意見なし」を「よい」と読み替えないこと。**
    """
    if _load() is None:
        return None
    was = is_unit(before)
    if was:
        return False
    now = is_common_unit(after)
    if now is None:
        return None
    return bool(now) and was is False
