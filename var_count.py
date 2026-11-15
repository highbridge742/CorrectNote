# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""数を表す英字1字＋助数詞（n個め・n回目・k番目・m人）の英字を、任意の数として直さない
（2026-11-15 うに「n個めという、任意の数字を表す表現のnが補正される。アルファベットの母音紛れ扱いされていると思う」）。

なぜ
----
英字1字のすぐ後ろに助数詞（個・回・番目・人・件・倍）が続く形は、数字の代わりに文字を置いた書き方。ローマ字入力の
打ち残し（ん の n）や母音の紛れと見て消したり紫にしたりすると、正しい文を壊す。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
英字1字（前後が英字・数字でない）を数字 1 に置いた行を解析し、その所が 数＋助数詞（1個・2回）になるなら、
数字に置いた行で補正して、その位置の数字を元の英字へ戻す（字数は同じなので紫の位置はそのまま）。
数字が直しで消えたときは、置かずに補正した元の答えを返す。特定の語には合わせない（英字1字と品詞の並びだけで見る）。
切り替え: CN_VAR_COUNT=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}
_MASK = '1'
_BEFORE = ('記号', '助詞', '連体詞', '接頭詞')
_KANJI_NUM = '〇一二三四五六七八九十百千万億兆'


def _on():
    return os.environ.get('CN_VAR_COUNT') != '0'


def _latin(c):
    return ('a' <= c <= 'z') or ('A' <= c <= 'Z') or ('ａ' <= c <= 'ｚ') or ('Ａ' <= c <= 'Ｚ')


def _digit(c):
    return '0' <= c <= '9' or '０' <= c <= '９'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def spots(line):
    """数を表す英字1字の位置の並び。"""
    if not isinstance(line, str):
        return []
    cand = []
    for i, c in enumerate(line):
        if not _latin(c) or i + 1 >= len(line) or not _kanji(line[i + 1]):
            continue
        if i > 0 and (_latin(line[i - 1]) or _digit(line[i - 1])):
            continue
        cand.append(i)
    if not cand:
        return []
    masked = mask(line, cand)
    try:
        from morphology import tokenize
        toks = list(tokenize(masked))
    except Exception:
        return []
    out = []
    for i in cand:
        k = next((j for j, t in enumerate(toks) if t.start == i), None)
        if k is None:
            continue
        t = toks[k]
        p = toks[k - 1] if k else None
        if p is not None and p.pos not in _BEFORE:
            # 数の代わりの英字は語の切れ目に立つ（行頭・記号・助詞・この・第／全 の後ろ）。語の途中や名詞のすぐ後ろの英字
            # （さm歩・車ｄ目）はローマ字の打ち残しなので見ない（2026-11-15 補正担当、作った誤字692行の6行）
            continue
        if t.surface == _MASK:
            q = toks[k + 1] if k + 1 < len(toks) else None
            if (t.pos_sub or '').startswith('数') and q is not None and '助数詞' in (q.pos_sub or '') and q.start == t.end:
                out.append(i)
        elif (t.surface[:1] == _MASK and len(t.surface) == 2 and _kanji(t.surface[1]) and t.surface[1] not in _KANJI_NUM
              and t.pos == '名詞'):
            # 数字と1字がまとまった語（1個・3人）。漢数字（1二）は数の続きで助数詞ではないので見ない（佑b二極 の打ち違い）
            out.append(i)
    return out


def mask(line, at):
    s = list(line)
    for i in at:
        s[i] = _MASK
    return ''.join(s)


def _unmask(line, masked, result, at):
    got = result.get('corrected')
    if not isinstance(got, str):
        return None
    out = list(got)
    m = difflib.SequenceMatcher(None, masked, got, autojunk=False)
    for i in at:
        j = None
        for tag, a1, a2, b1, _b2 in m.get_opcodes():
            if tag == 'equal' and a1 <= i < a2:
                j = b1 + (i - a1)
                break
        if j is None or out[j] != _MASK:
            return None
        out[j] = line[i]
    res = dict(result)
    res['corrected'] = ''.join(out)
    if 'original' in res:
        res['original'] = line      # 答えの元の行は頼まれた行（伏せ字の行のままだとタブを済みにできない・2026-11-15）
    if res['corrected'] == line and 'changed' in res:
        res['changed'] = False
    return res


def correct_line(line, *args, **kwargs):
    at = []
    if _on():
        try:
            at = spots(line)
        except Exception:
            at = []
    if not at:
        return _orig['correct_line'](line, *args, **kwargs)
    masked = mask(line, at)
    try:
        r = _orig['correct_line'](masked, *args, **kwargs)
        back = _unmask(line, masked, r, at) if isinstance(r, dict) else None
    except Exception:
        back = None
    if back is not None:
        return back
    return _orig['correct_line'](line, *args, **kwargs)


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
