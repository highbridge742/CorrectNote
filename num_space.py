# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""数字の前後の空白1つ（最大 30 日間・1 回分・リカバリー 90錠）は、見やすくするための書き方で、語の区切りではない。

なぜ
----
解析は空白で語を切るので、「1 回分」の 回分 が数の後ろの助数詞と分からず、別の語（回文）に替えたり、
「30 日間無料」「2 か月後」の後ろ半分を珍しい語として紫にしたりした（2026-11-21 うに 誤判定タブ）。
空白を抜いた行では正しく読める。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。
1. 数字（半角・全角）と、かな・漢字・片仮名の間に挟まった空白1つ（半角・全角）を抜いた行を作る。
2. 抜いた行を補正に通し、答えの位置を元の行の位置に戻す。抜いた空白の所に掛かる書き換えは採らない
   （その時は元の行のままの答え）。
3. 抜く空白が無い行は前のまま。

切り替え: CN_NUM_SPACE=0 で前のまま。特定の語や文字列には合わせない。
"""
import difflib
import functools
import os
import re

_orig = {}
_SP = ' 　'
_DIG = '0-9０-９'
_JA = '぀-ヿ一-鿿々'
_PAT = re.compile('(?<=[%s])[%s](?=[%s])|(?<=[%s])[%s](?=[%s])' % (_DIG, _SP, _JA, _JA, _SP, _DIG))


def _squeeze(line):
    """(抜いた行, 抜いた行の各字の元の位置, 抜いた空白の元の位置)"""
    gone = [m.start() for m in _PAT.finditer(line)]
    if not gone:
        return line, None, ()
    g = set(gone)
    pos = [i for i in range(len(line)) if i not in g]
    return ''.join(line[i] for i in pos), pos, tuple(gone)


def _back(pos, n, a, b):
    """抜いた行の [a, b) を元の行の位置へ"""
    if a >= len(pos):
        return n, n
    s = pos[a]
    e = pos[b - 1] + 1 if b > a else s
    return s, e


def _map_spans(spans, pos, n):
    out = []
    for x in spans or ():
        try:
            a, b = _back(pos, n, int(x[0]), int(x[1]))
        except Exception:
            return None
        out.append(type(x)([a, b] + list(x[2:])) if isinstance(x, list) else tuple([a, b] + list(x[2:])))
    return out


def _rebuild(line, sq, got, pos, gone):
    """抜いた行の答え got に、抜いた空白を戻した行と、その行の各字の位置の写し。戻せないなら None"""
    ops = difflib.SequenceMatcher(None, sq, got, autojunk=False).get_opcodes()
    g = sorted(gone)
    out = []
    gmap = []            # got の各字 → 戻した行の位置
    k = 0
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            for d in range(i2 - i1):
                i = i1 + d
                while k < len(g) and g[k] < pos[i]:
                    out.append(line[g[k]])
                    k += 1
                gmap.append(len(out))
                out.append(got[j1 + d])
        else:
            # 書き換えの所に抜いた空白が挟まるなら戻せない
            lo = pos[i1] if i1 < len(pos) else len(line)
            hi = pos[i2 - 1] if i2 > i1 else lo
            if any(lo < x < hi for x in g[k:]):
                return None
            while k < len(g) and i1 < len(pos) and g[k] < pos[i1]:
                out.append(line[g[k]])
                k += 1
            for j in range(j1, j2):
                gmap.append(len(out))
                out.append(got[j])
    while k < len(g):
        out.append(line[g[k]])
        k += 1
    return ''.join(out), gmap


def _map_got(spans, gmap, total):
    out = []
    for x in spans or ():
        a, b = int(x[0]), int(x[1])
        s = gmap[a] if a < len(gmap) else total
        e = gmap[b - 1] + 1 if b > a and b - 1 < len(gmap) else s
        out.append(type(x)([s, e] + list(x[2:])) if isinstance(x, list) else tuple([s, e] + list(x[2:])))
    return out


def correct_line(line, *a, **k):
    f = _orig['correct_line']
    if os.environ.get('CN_NUM_SPACE') == '0' or not isinstance(line, str):
        return f(line, *a, **k)
    sq, pos, gone = _squeeze(line)
    if pos is None:
        return f(line, *a, **k)
    r = f(sq, *a, **k)
    if not isinstance(r, dict):
        return f(line, *a, **k)
    got = r.get('corrected') or sq
    n = len(line)
    out = dict(r)
    out['original'] = line
    for key in ('odd_spans', 'odd_reasons', 'unsure_spans', 'original_spans'):
        if key in r:
            m = _map_spans(r.get(key), pos, n)
            if m is None:
                return f(line, *a, **k)
            out[key] = m
    if got == sq:
        out['corrected'] = line
        out['changed'] = False
        if 'spans' in r:
            out['spans'] = []
        return out
    rb = _rebuild(line, sq, got, pos, gone)
    if rb is None:
        return f(line, *a, **k)
    fixed, gmap = rb
    out['corrected'] = fixed
    out['changed'] = fixed != line
    if 'spans' in r:
        out['spans'] = _map_got(r.get('spans'), gmap, len(fixed))
    return out


def install():
    if _orig or os.environ.get('CN_NUM_SPACE') == '0':
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
