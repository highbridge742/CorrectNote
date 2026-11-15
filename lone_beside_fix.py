# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""直した所のすぐ前に、助詞も無く浮いた1字の漢字が残るなら、その字に紫を付ける（2026-11-13 補正担当、
全体評価のリリース前の検査: 誤字の語の後ろ半分だけを直して、前の1字が取り残される形）。

作った例: 金額が［口枷］って（まちがって の打ち違い）の 枷って だけを 変わって に直すと「金額が口変わって」になり、
口 は前の語にも後ろの動詞にも付かない1字として残る。直しそのものは前からの段の答えなので変えず、残った字に紫だけ足す。
- 直した所の頭が動詞か形容詞で、そのすぐ前（間に字なし）が keyslip_window._lone_kanji の言う浮いた1字の名詞のとき。
- 紫は元の行の位置。その字に紫が掛かっていなければ足す。文は書き換えない。
correction_entry.correct_line を外から包む。CN_LONE_BESIDE_FIX=0 で前のまま。
"""
import difflib
import os

REASON = '直した所の前に、語に付かない1字が残った'
_orig = {}


def _on():
    return os.environ.get('CN_LONE_BESIDE_FIX') != '0'


def lone_spans(line, got):
    """直した行 got の、直した所のすぐ前に残る浮いた1字の、元の行 line での位置 [(始め, 終わり)]。"""
    if not got or got == line:
        return []
    from morphology import tokenize
    import keyslip_window as KW
    toks = list(tokenize(got))
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes():
        if tag == 'equal' or j1 == 0 or i1 == 0:
            continue
        k = next((n for n, t in enumerate(toks) if t.start == j1), None)
        if k is None or k == 0:
            continue
        head, prev = toks[k], toks[k - 1]
        if head.pos not in ('動詞', '形容詞') or prev.end != j1 or len(prev.surface) != 1:
            continue
        if line[i1 - 1] != prev.surface:
            continue
        try:
            lone = KW._lone_kanji(prev, toks, k - 1)
        except Exception:
            lone = False
        if lone:
            out.append((i1 - 1, i1))
    return out


def mark(line, result):
    if not _on() or not isinstance(result, dict) or not isinstance(line, str):
        return result
    try:
        add = lone_spans(line, result.get('corrected') or line)
    except Exception:
        return result
    odd = list(result.get('odd_spans') or ())
    add = [x for x in add if not any(o[0] < x[1] and x[0] < o[1] for o in odd)]
    if not add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(odd + [list(x) for x in add], key=lambda x: tuple(x[:2]))
    out['odd_reasons'] = sorted(list(result.get('odd_reasons') or ()) + [[a, b, REASON] for a, b in add],
                                key=lambda x: tuple(x[:2]))
    return out


def correct_line(line, *a, **k):
    return mark(line, _orig['correct_line'](line, *a, **k))


def install():
    if _orig or not _on():
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    # 包みの外から元の引数（defer_heavy・tab_has_kana など）が見えるように（analysis_worker が inspect.signature で見る・2026-11-13）
    import functools
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True
