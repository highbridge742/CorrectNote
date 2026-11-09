# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""離れた場所が同時に変わった時、間の変わっていない行を見つける（2026-11-05）。

行の差分は「頭と尻の同じ行」だけを見るので、離れた2か所が1回の編集で変わると、その間の行も全部
「変わった」ことになる（箇条書きで簡易入力の行を集めた時、100行のタブで90行が未解析になり78行を解き直した）。
間の行を順序どおりに当てて、同じ本文の行の答えを持ち越す。それぞれの変更を1つずつ行った時と同じ扱いにするので、
変更の近くの行は今までどおり解き直す（near_changes）。"""
from difflib import SequenceMatcher

MIN_MIDDLE = 4          # ふつうの打鍵（1〜3行）は当てない
MAX_MIDDLE = 5000       # これより大きい範囲は今までどおり（当てる時間のほうが高くつく）


def carried_rows(old, new, head, tail):
    """{今の行番号: 前の行番号}。head と tail の間で、本文が同じで順序も同じ行。"""
    old_end, new_end = len(old) - tail, len(new) - tail
    if not (MIN_MIDDLE <= old_end - head <= MAX_MIDDLE and MIN_MIDDLE <= new_end - head <= MAX_MIDDLE):
        return {}
    blocks = SequenceMatcher(None, old[head:old_end], new[head:new_end], autojunk=False).get_matching_blocks()
    carried = {}
    for block in blocks:
        for k in range(block.size):
            carried[head + block.b + k] = head + block.a + k
    return carried


def near_changes(carried, head, new_end, line_count, radius):
    """持ち越した行のうち、変更のすぐ近くの行（文脈が変わるので解き直す）。"""
    near = set()
    previous = None
    for row in sorted(carried):
        if previous is None:
            joined = row == head and carried[row] == head
        else:
            joined = row == previous + 1 and carried[row] == carried[previous] + 1
        if not joined:
            # 変更の境目: この行の上と、前に持ち越した行の下
            near.update(range(max(0, row), min(line_count, row + radius)))
            if previous is not None:
                near.update(range(max(0, previous - radius + 1), previous + 1))
        previous = row
    if previous is not None and previous + 1 != new_end:
        near.update(range(max(0, previous - radius + 1), previous + 1))
    return sorted(near & set(carried))
