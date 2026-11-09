# -*- coding: utf-8 -*-
"""副助詞＋の＋用言（などのした）の の を、隣のキーの格助詞の打ち違い（などにした）として見る（2026-11-09 手分けA）。

連体の の（解析の 連体化）は後ろに名詞が要る。副助詞（など・だけ・まで…）の後ろの の のすぐ後ろに自立の用言が来る形は、
文の形にならない（○ 本などの棚・○ 本などにした）。かな入力・ローマ字入力それぞれで、の と1打違い（隣のキー）の
格助詞に置き換えて、行の並びの費用（morphology.path_cost）を比べる。
- 一番よい候補が元の行より MARGIN 以上よく、二番の候補ともそれだけ離れるなら直す。そうでなければ紫。
打った記録も IME も使わない。特定の語には合わせない。CN_NO_PARTICLE_SLIP=0 で見ない。
"""
import difflib
import os

MARGIN = 1000
_CASES = ('に', 'を', 'が', 'で', 'と', 'も', 'は', 'へ')


def _on():
    return os.environ.get('CN_NO_PARTICLE_SLIP') != '0'


def propose(text, input_method='kana'):
    """[(開始, 終了, 直し or None)]"""
    import corrector
    import morphology
    toks = list(morphology.tokenize(text))
    out = []
    for i in range(1, len(toks) - 1):
        a, p, v = toks[i - 1], toks[i], toks[i + 1]
        if p.surface != 'の' or p.pos != '助詞' or not (p.pos_sub or '').startswith('連体化'):
            continue
        if a.pos != '助詞' or not (a.pos_sub or '').startswith('副助詞') or a.end != p.start or p.end != v.start:
            continue
        if v.pos not in ('動詞', '形容詞') or not (v.pos_sub or '').startswith('自立'):
            continue
        # 用言と解析された所が送り仮名の無い漢字だけ（誤｜配送 の 誤）なら、接頭の漢字＋名詞の熟語を解析が切っただけで、
        # 後ろには名詞が在る（2026-11-09 うに: 正しい文の などの誤補正 を などに にしていた）。CN_NPS_KANA_VERB=0 で前のまま
        if (os.environ.get('CN_NPS_KANA_VERB') != '0'
                and not any('ぁ' <= c <= 'ゖ' for c in v.surface)):
            continue
        here = morphology.path_cost(text)
        if here is None:
            continue
        scored = []
        for c in _CASES:
            if not corrector.adjacent_slip('の', c, input_method):
                continue
            cost = morphology.path_cost(text[:p.start] + c + text[p.end:])
            if cost is not None:
                scored.append((cost, c))
        if not scored:
            continue
        scored.sort()
        best = scored[0]
        second = scored[1][0] if len(scored) > 1 else here
        sure = best[0] <= here - MARGIN and best[0] <= second - MARGIN
        out.append((p.start, p.end, best[1] if sure else None))
    return out


def repair_line(line, result, input_method='kana', decided=()):
    if not _on() or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, input_method)
    except Exception:
        return result
    if not marks:
        return result
    ops = difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes()
    changed = [(o[1], o[2]) for o in ops if o[0] != 'equal']

    def overlaps(a, b, spans):
        return any(x < b and a < y for x, y in spans)
    new, odd_add, details = done, [], []
    for s, e, rep in sorted(marks, reverse=True):
        if overlaps(s, e, changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or overlaps(org[0], org[1], list(decided or ())):
            continue
        if rep:
            new = new[:s] + rep + new[e:]
            details.append([done[s:e], rep, '打ち違い'])
        else:
            odd_add.append(org)
    if new == done and not odd_add:
        return result
    out = dict(result)
    if new != done:
        lops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
    if odd_add:
        now = [tuple(x[:2]) for x in out.get('odd_spans') or ()]
        out['odd_spans'] = sorted(set(now) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, '「の」の後ろに名詞が無く、用言が続いています。隣のキーの助詞かもしれません') for a, b in odd_add]
    return out
