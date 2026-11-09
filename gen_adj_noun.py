# -*- coding: utf-8 -*-
"""名詞＋の＋形容詞 で行（文）が終わる所（私の｜重い）を、形容詞と同じ読みの名詞（思い）の選び違いとして見る
（2026-11-09 手分けA）。

の の後ろの形容詞の言い切りは、後ろに名詞が無ければ文の形にならない（○ 私の重い荷物・○ 私は重い）。IME が同じ読みの
名詞を形容詞に変換した形なので、その読みの名詞を探す。
- 見る所: 名詞（代名詞を含む）＋の＋漢字の形容詞の基本形 で、形容詞の後ろが行の終わりか句読点・記号。
- 候補: 形容詞の読み（おもい）と同じ読みの、漢字を含む名詞。固有名詞・人名は除く。
- 一般の文で形容詞より身近な（ime_reconvert._rank が小さい）候補が1つなら直す。2つ以上なら紫。0なら何もしない
  （背の高い・遺体／痛い は形容詞の方が身近なので触らない）。
打った記録も IME も使わない（雲と PC で同じ答え）。特定の語には合わせない。CN_GEN_ADJ_NOUN=0 で見ない。
"""
import difflib
import os


def _on():
    return os.environ.get('CN_GEN_ADJ_NOUN') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _candidates(adj, reading):
    import reading_lattice
    import ime_reconvert as R
    reading_lattice.load()
    here = R._rank(adj)
    out = set()
    for s, _l, _r, _c, pos in reading_lattice._table.get(reading, ()):
        if pos != '名詞' or not any(_kanji(c) for c in s) or R._rank(s) > here:
            continue
        try:
            from morphology import tokenize
            toks = list(tokenize(s))
            if len(toks) != 1 or toks[0].pos != '名詞' or (toks[0].pos_sub or '').startswith('固有名詞'):
                continue
        except Exception:
            continue
        out.add(s)
    return out


def propose(text):
    """[(開始, 終了, 直し or None)]"""
    from morphology import tokenize
    toks = list(tokenize(text))
    marks = []
    for i in range(2, len(toks)):
        a, p, n = toks[i], toks[i - 1], toks[i - 2]
        if a.pos != '形容詞' or (a.pos_sub or '') != '自立' or (getattr(a, 'infl_form', '') or '') != '基本形':
            continue
        if not _kanji(a.surface[0]) or p.surface != 'の' or p.pos != '助詞' or n.pos != '名詞':
            continue
        if p.start != n.end or a.start != p.end:
            continue
        if i + 1 < len(toks) and toks[i + 1].pos != '記号':
            continue
        cands = _candidates(a.surface, _hira(a.reading))
        if not cands:
            continue
        marks.append((a.start, a.end, next(iter(cands)) if len(cands) == 1 else None))
    return marks


def repair_line(line, result, decided=()):
    if not _on() or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done)
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
            details.append([done[s:e], rep, '同じ読みの名詞'])
        else:
            odd_add.append(org)
    if new == done and not odd_add:
        return result
    out = dict(result)
    if new != done:
        d_spans = [(s, e) for s, e, rep in marks if rep]
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [x for x in out[key] if not overlaps(x[0], x[1], d_spans)]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [r for r in out['odd_reasons'] if not overlaps(r[0], r[1], d_spans)]
        lops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
    if odd_add:
        now = [tuple(x[:2]) for x in out.get('odd_spans') or ()]
        out['odd_spans'] = sorted(set(now) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, 'の の後ろの形容詞で文が終わっています。同じ読みの名詞かもしれません') for a, b in odd_add]
    return out
