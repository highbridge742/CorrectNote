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

"""異様判定後の候補用。内蔵辞書の用言と活用形を読みから引く。

一般の名詞候補に掛かる新聞頻度の敷居を、活用形へ流用しない。
個人履歴は作らず、既存のDictIndexと同じ走査・派生キャッシュを共有する。
"""
from functools import lru_cache


def include_entry(surface, reading, pos, sub):
    """名詞向け頻度で落とさず、用言の実辞書項を既存索引へ収める。"""
    return (2 <= len(surface) <= 18 and pos in ('動詞','形容詞')
            and sub in ('自立','非自立') and bool(reading)
            and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in reading)
            and all('ぁ' <= c <= 'ゖ' or '一' <= c <= '鿿' or c in '々ー' for c in surface))


@lru_cache(maxsize=8192)
def dictionary_readings(surface):
    """単語・活用形の完全一致の読み。候補名詞の頻度による刈り込み前に引く。"""
    import morphology as m
    if not m.HAS_JANOME:
        return ()
    with m._TOKENIZE_LOCK:
        entries = [entry for entry in m._TOKENIZER.sys_dic.lookup(
            surface.encode('utf-8'), m._TOKENIZER.matcher) if entry[1] == surface]
        rows = [(entry[4], m._TOKENIZER.sys_dic.lookup_extra(entry[0])[4]) for entry in entries]
    # lookup の word cost と読みで安定させる。同じ読みの複数の品詞を重ねない。
    return tuple(dict.fromkeys(m.katakana_to_hiragana(reading)
                               for _, reading in sorted(rows)))


@lru_cache(maxsize=8192)
def has_nominal_entry(surface):
    """活用形を文中で誤分割した名詞列と、辞書に実在する名詞を区別する。"""
    import morphology as m
    if not m.HAS_JANOME:
        return False
    with m._TOKENIZE_LOCK:
        entries = m._TOKENIZER.sys_dic.lookup(surface.encode('utf-8'), m._TOKENIZER.matcher)
        return any(e[1] == surface and
                   m._TOKENIZER.sys_dic.lookup_extra(e[0])[0].startswith('名詞,') for e in entries)
