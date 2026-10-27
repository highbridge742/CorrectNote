# -*- coding: utf-8 -*-
"""後ろに て・た の続かない音便形の動詞（くだい・置い）を、抜けたかな1字を足して直す（2026-10-26・未解決 くだい）。

    提案してみてくだい。 → 提案してみてください。

動詞の連用タ接続（イ音便・撥音便・促音便: 砕い・休ん・待っ）は、後ろに て／で／た／だ（たり・たら・ても…）が続いて
初めて文になる。続かないなら、どこかの1字が抜けている（打ち落とし）。その動詞の中か直後に、かな1字を足した形のうち、
足した後に同じ形が残らず、その辺りの語が全部読みを持つものを行の費用（morphology.path_cost）で並べる。
一番が二番より MARGIN 以上軽ければそれに置き、並べば紫（迷うなら紫）。語を名指しした表は持たない。
"""
import difflib

MARGIN = 1000
_FOLLOW = ('て', 'で', 'た', 'だ', 'たり', 'だり', 'ちゃ', 'じゃ', 'たら', 'だら', 'ても', 'でも')
_KANA = tuple(chr(c) for c in range(0x3041, 0x3094) if chr(c) not in 'ぁぃぅぇぉゎゐゑ')


def dangling(text):
    from morphology import tokenize
    return [(t.start, t.end) for t in tokenize(text)
            if t.pos == '動詞' and t.infl_form == '連用タ接続' and not text[t.end:].startswith(_FOLLOW)]


def propose(text):
    """[(開始, 終了, 置く文字列 or None)]（text の位置）。"""
    from morphology import tokenize, path_cost
    found = dangling(text)
    if not found:
        return []
    out = []
    s, e = found[0]
    cands = []
    for p in range(s, e + 1):
        for h in _KANA:
            t = text[:p] + h + text[p:]
            if dangling(t):
                continue
            if not all(x.has_reading for x in tokenize(t) if x.end > s and x.start < e + 1):
                continue
            c = path_cost(t)
            if c is not None:
                cands.append((c, t))
    cands.sort()
    if cands and (len(cands) == 1 or cands[1][0] - cands[0][0] >= MARGIN):
        out.append((s, e, cands[0][1][s:e + 1]))
    else:
        out.append((s, e, None))
    return out


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    s, e, rep = marks[0]
    if any(x < e and s < y for x, y in changed):
        return result
    org = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= s and e <= i2:
            org = (s - i1 + j1, e - i1 + j1)
    if org is None or any(x < org[1] and org[0] < y for x, y in list(odd_now) + list(decided or ())):
        return result
    out = dict(result)
    if rep is None:
        out['odd_spans'] = sorted(set(odd_now) | {org})
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (org[0], org[1], f'「{line[org[0]:org[1]]}」の後ろに続くはずの て・た がありません')]
        return out
    new = done[:s] + rep + done[e:]
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + [[done[s:e], rep, '抜けた1字']],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
