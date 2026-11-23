# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""「X」はあまり使わない語です の紫で、答えの行では X がもう1語として立っていない（前の字を直して 画像 の一部に
なった）ものを外す。

なぜ
----
IME の変換し直しの段は、壊れた字の隣の1字（が゛｜像）を珍しい語と見て紫を付ける。後の段が壊れた字を直すと
（が゛→画）その字は 画像 の一部になるが、紫と訳は前の行の所のまま残る（2026-11-22 うに 変換タブ 130 行）。
訳が指す語が答えに無いので、その紫は根拠を失っている。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。答えの行が打った行と違い、
紫に掛かる訳が全部「「X」はあまり使わない語です」で、答えの行のその所に X とちょうど同じ語が無く、X を含む
もっと長い辞書の語があるときだけ、その紫と訳を外す。字は変えない。CN_STALE_WORD_PURPLE=0 で前のまま。
"""
import difflib
import functools
import os
import re

_orig = {}
_RARE = re.compile('「(.+?)」はあまり使わない語です')


def filter_result(line, result):
    if os.environ.get('CN_STALE_WORD_PURPLE') == '0' or not isinstance(result, dict):
        return result
    text = result.get('corrected') or line
    odd = result.get('odd_spans') or []
    reasons = result.get('odd_reasons') or []
    if text == line or not odd or not reasons:
        return result
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return result
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()

    def pos(p, end):
        # 紫の所は打った行の位置（line_coords）。答えの行の位置へ写す
        for tg, i1, i2, j1, j2 in ops:
            if i1 <= p < i2 or (end and i1 < p <= i2):
                return j1 + (p - i1) if tg == 'equal' else (j2 if end else j1)
        return len(text) if end else 0
    dropped = set()
    for o in odd:
        a, b = o[0], o[1]
        why = [r for r in reasons if len(r) >= 3 and r[0] < b and a < r[1]]
        if not why:
            continue
        ok = True
        for r in why:
            m = _RARE.match(str(r[2]))
            if not m:
                ok = False
                break
            x = m.group(1)
            if line[r[0]:r[1]] != x:
                ok = False
                break
            s0, e0 = pos(r[0], False), pos(r[1], True)
            here = [t for t in toks if t.start < max(e0, s0 + 1) and s0 < t.end]
            if any(t.surface == x for t in here) or not any(
                    x in t.surface and len(t.surface) > len(x) and getattr(t, 'has_reading', False) for t in here):
                ok = False
                break
        if ok:
            dropped.add((a, b))
            dropped.update((r[0], r[1]) for r in why)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = [o for o in odd if (o[0], o[1]) not in dropped]
    out['odd_reasons'] = [r for r in reasons if (r[0], r[1]) not in dropped]
    if out.get('unsure_spans'):
        out['unsure_spans'] = [o for o in out['unsure_spans'] if (o[0], o[1]) not in dropped]
    return out


def correct_line(line, store, *a, **k):
    r = _orig['correct_line'](line, store, *a, **k)
    if os.environ.get('CN_STALE_WORD_PURPLE') == '0' or not isinstance(line, str):
        return r
    try:
        return filter_result(line, r)
    except Exception:
        return r


def install():
    if _orig or os.environ.get('CN_STALE_WORD_PURPLE') == '0':
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True


def uninstall():
    if not _orig:
        return
    import correction_entry
    correction_entry.correct_line = _orig.pop('correct_line')
