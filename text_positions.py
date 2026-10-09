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

"""Pure cursor and selection projection shared by correction and the editor."""


def map_column(original, corrected, col, edge=None):
    """
    行を書き換えたとき、カーソルの桁を新しい行の対応する場所へ移す。

    統合表示の自動反映は行をまるごと入れ替えるので、そのままだと
    カーソルが行頭へ飛ぶ。書き換えの前後で「同じところ」を指し
    続けるように、差分を見て桁を読み替える。

    考え方:
      - 変わっていない部分に居るなら、そのぶんだけずらす
      - 書き換えられた部分の中に居るなら、その**終わり**へ置く
        （打っている途中の語が直った場合、続きは語の後ろから
          書きたいはずなので）
      - 行末に居たなら、新しい行末へ

    純粋関数にしてあるので、画面なしで検証できる。
    """
    if col <= 0:
        return 0
    if col >= len(original):
        return len(corrected)
    if original == corrected:
        return col
    import difflib
    sm = difflib.SequenceMatcher(None, original, corrected, autojunk=False)
    operations = sm.get_opcodes()
    if edge is not None:
        # 選択端はカーソルと異なる。変化した語の先頭を末尾へ送らない。
        for tag, i1, i2, j1, j2 in operations:
            if tag == 'insert' and i1 == col:
                return j2 if edge == 'start' else j1
        for tag, i1, i2, j1, j2 in operations:
            if i1 <= col <= i2:
                if tag == 'equal':
                    return j1 + col - i1
                if col == i1:
                    return j1
                if col == i2:
                    return j2
                return j1 if edge == 'start' else j2
    for tag, i1, i2, j1, j2 in operations:
        if not (i1 <= col < i2 or (tag == 'insert' and i1 == col)):
            continue
        if tag == 'equal':
            return j1 + (col - i1)
        return j2
    return min(col, len(corrected))


def selection_correction_pair(original, corrected, start, end, source=True):
    """Project exact selection edges; never widen an edge inside a changed word."""
    import difflib
    shown,other=(original,corrected) if source else (corrected,original)
    if not 0<=start<end<=len(shown):return None
    if shown==other:return shown[start:end],shown[start:end],start,end
    edits=difflib.SequenceMatcher(None,shown,other,autojunk=False).get_opcodes()
    if any(tag!='equal' and any(a<edge<b for edge in (start,end))
           for tag,a,b,_,_ in edits):return None
    lo=map_column(shown,other,start,edge='start')
    hi=map_column(shown,other,end,edge='end')
    before,after=(shown[start:end],other[lo:hi]) if source else (other[lo:hi],shown[start:end])
    return (before,after,lo,hi) if before and after else None


