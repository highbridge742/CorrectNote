# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""名詞＋格助詞＋副助詞（など・なんか・とか）＋同じ格助詞 の並びで、前の格助詞を余分な打鍵として外す
（2026-11-14 補正担当・未解決タブ「原文の文脈がおかしい」の型。作った例: 本をなどを読んだ → 本などを読んだ）。

なぜ
----
副助詞 など は名詞にじかに付き、格助詞はその後ろに来る（本などを）。同じ格助詞が など の前後に2つ並ぶ形は、
書き直しの途中で前の格助詞が残った打ち過ぎ。後ろの格助詞が文の形を作るので、前を外すと1つに決まる。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
書き換えの無い行で、その並びの前の格助詞か副助詞に紫が掛かる所だけを直す（紫の無い所は見ない）。
特定の語や文字列には合わせない（品詞と並びだけで見る）。切り替え: CN_PARTICLE_DUP=0 で前のまま。
"""
import difflib
import functools
import os

_ADVERBIAL = ('など', 'なんか', 'とか')
_orig = {}


def _on():
    return os.environ.get('CN_PARTICLE_DUP') != '0'


def spots(text):
    """[(前の格助詞の始め, 終わり)]"""
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return []
    out = []
    for i in range(1, len(toks) - 2):
        n, p1, q, p2 = toks[i - 1], toks[i], toks[i + 1], toks[i + 2]
        if (n.pos == '名詞' and p1.pos == '助詞' and (p1.pos_sub or '').startswith('格助詞')
                and q.pos == '助詞' and (q.pos_sub or '').startswith('副助詞') and q.surface in _ADVERBIAL
                and p2.surface == p1.surface and p2.pos == '助詞' and (p2.pos_sub or '').startswith('格助詞')
                and n.end == p1.start and p1.end == q.start and q.end == p2.start):
            out.append((p1.start, p1.end, q.end))
    return out


def fix(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line:
        return result
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    if not odd:
        return result
    hits = [(a, b, e) for a, b, e in spots(line) if any(x < e and a < y for x, y in odd)]
    if not hits:
        return result
    new = line
    for a, b, _e in sorted(hits, reverse=True):
        new = new[:a] + new[b:]
    out = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']

    def keep(x):
        return not any(x[0] < e and a < x[1] for a, _b, e in hits)
    out.update({'corrected': new, 'changed': True, 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'odd_spans': [x for x in result.get('odd_spans') or () if keep(x)],
                'odd_reasons': [r for r in result.get('odd_reasons') or () if keep(r)],
                'details': list(result.get('details') or ()) + [[line[a:b], '', '余分な助詞'] for a, b, _e in hits]})
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        return fix(line, result)
    except Exception:
        return result


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
