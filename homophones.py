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
**同音異義語の読みか**を答える（項目48-QH・2026-09-05）。

うにさんの指定（2026-09-05）:

    「この回数を記録する仕組みを削除します。
      代わりに**同音異義語の一覧表**を作成し、最後にどの変換をしたか、
      それぞれ履歴1回分記録します。
      **同音異義語ではない単語の回数は残しません**」

＝ 覚えてよいのは「同音異義語の読み」だけ。だから**何が同音異義語か**を
決める場所が要る。**一覧表は手で書かない**——同梱の辞書と本人の語彙から
導く。手で書くと、載っていない読み（うにさんが打つ語のほとんど）が
永久に対象外になるうえ、名簿が2つになる（決めているのは最初の行）。

判定はこれだけ:

    同梱の辞書がその読みに **漢字を含む表記を2つ以上**持つ
      or **本人の語彙に**その読みの表記が **2つ以上**ある

    かんしん  → 関心・感心・歓心   … 同音異義語
    こうえん  → 公園・講演・後援   … 同音異義語
    もじにゅうりょく → 文字入力 だけ … ちがう（枠を持たない）

**辞書の側だけ「漢字を含む」を要るとした理由**: 辞書は同じ読みに
活用形や送り仮名違いを大量に持つので、そこまで拾うと枠が
ほとんどの読みに立ってしまう。うにさんの言う同音異義語は
「**対の単語に合わせる形で同じ意味を持つもの**」（的リストの定義・
`homophone_pairs.py` の冒頭）であって、書き分けの話ではない。

**本人の語彙の側は、2つ以上あればそれでよい**（漢字を要らない）。
本人が同じ読みで2通り書いているなら、**その人にとっては書き分けの
必要がある読み**である——`たん`／`痰`・`つながり`／`繋がり` の類。
回数を廃した以上、どちらを採るかを決められるのは枠だけになった。
"""

_MIN_SURFACES = 2


def _has_kanji(text):
    """
    漢字を含むか。範囲は `corrector.is_kanji` と**同じ**
    （U+4E00〜U+9FFF）。**借りずに書いてある**のは、この judgment が
    引き当ての内側から呼ばれるためで、`corrector` を読み込むと
    環になる（`corrector` → `vocabulary` → `last_choice` → ここ）。
    **範囲を変えるときは両方**（48-GN の例外——同じ「文字の種類」で、
    判定ではない）。
    """
    return any('一' <= c <= '鿿' for c in (text or ''))


def is_homophone_reading(reading, store=None, dict_index=None):
    """
    その読みは**同音異義語の読み**か（項目48-QH）。

    `store`（本人の語彙）・`dict_index`（同梱の辞書索引）のどちらも
    無ければ False（意見なし）。**どちらか一方でも 2 つ以上の
    漢字表記を知っていれば True。**

    引き当ての道の内側から呼ばれるので、**例外は外へ出さない**。
    """
    if not reading:
        return False
    if dict_index is not None:
        try:
            seen = set()
            for s in dict_index.surfaces_for_reading(reading):
                if _has_kanji(s):
                    seen.add(s)
                    if len(seen) >= _MIN_SURFACES:
                        return True
        except Exception:
            pass
    if store is not None:
        try:
            own = {e.get('surface') for e in store.lookup(reading)}
            own.discard('')
            own.discard(None)
            if len(own) >= _MIN_SURFACES:
                return True
        except Exception:
            pass
    return False


def surfaces_for_reading(reading, store=None, dict_index=None, limit=8):
    """
    その読みの**漢字を含む表記**を、辞書 → 本人の語彙の順に並べて返す
    （一覧を見せるための材料。判定そのものは上の関数）。
    """
    out = []
    seen = set()

    def _push(s):
        if s and _has_kanji(s) and s not in seen:
            seen.add(s)
            out.append(s)

    if dict_index is not None:
        try:
            for s in dict_index.surfaces_for_reading(reading):
                _push(s)
        except Exception:
            pass
    if store is not None:
        try:
            for e in store.lookup(reading):
                _push(e.get('surface') or '')
        except Exception:
            pass
    return out[:limit]
