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
"""
**カタカナの「断片」の表**（項目48-RO・2026-09-05）。

うにさんの報告（2026-09-05）:

    「`解析課背中セク、`——まず `背中セク` が異様なので**そう判定
      しないといけない**。**セクが組織名である判定が変**」

### なぜ表が要るか（表と読みでは割れないことが分かった）

`oddness._katakana_word_known` の出どころ4つのうち、**同梱の費用表**と
**世の読み**は、カタカナに対しては**読みの証拠であって綴りの証拠では
ない**。費用表は**読みごとにそのカタカナ綴りを表記として持つ**からで、

    せく → セク:35  咳く:145  堰く:145  塞く:146  急く:147
    ひと → ヒト:39  人:88          たんご → タンゴ:33  単語:93

2字の読み 3,036 のうち **1,838（60%）にカタカナ形が在り、たいてい最安**。
つまり `_table_cost('セク')` が値を返すのは「**せく と読む語が在る**」
という意味でしかない。世の読みも定義上そう。**2つとも綴りを見ていない。**

だから **AI の判定表**で割る（うにさんの指定 2026-08-24
「AI の判断を材料にしてよい。ただし**版と出どころを書く**」・
`kango_tier` と同じ型）。

    断片 ＝ 単独では日本語の語として立たない綴り（語の切れ端・
           打ち崩れ）。セク・イグ・ゼカ・ノジ
    語   ＝ 単独で使うカタカナ語（外来語・略語・感動詞・擬音）

**エンジンが引くのは断片の側だけ。** 語の側は既存の4つの出どころで
既に守られている（48-OY）。**迷ったものは表に載せない**（48-JJ——
載せ過ぎの害 ＞ 載せ漏れの害）。

**判定には使わない側面**: ここが返すのは「この綴りは語として立つか」
だけで、「異様か」は `oddness` が決める。表が無ければ**何も言わない**
（＝今までどおり）。
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
    for path in (os.path.join(here, 'katakana_frag.json'),
                 'katakana_frag.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            _TABLE = set(data.get('fragments') or ())
            return _TABLE
        except Exception:
            continue
    _MISSING = True
    return None


def available():
    return bool(_load())


def is_fragment(surface):
    """
    その綴りは**断片**か（表に載っていれば True）。

    表が読めない・載っていなければ **False**（＝意見なし。
    今までどおり既存の出どころで決める）。
    """
    t = _load()
    if not t:
        return False
    return surface in t
