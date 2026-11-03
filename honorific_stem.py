# -*- coding: utf-8 -*-
"""謙譲の「お＋動詞の連用形＋する」に、同じ読みの名詞が入った所を直す段（2026-10-30）。

「お持ちします」「お送りします」の お と する の間は動詞の連用形。そこに同じ読みの普通名詞（IME の選び違い）が入ると
「お＋名詞＋する」になる。名詞が動作の語（サ変の名詞）なら「お電話します」と言えるので、普通名詞のときだけ疑う。
同じ読みの動詞の連用形のうち身近なもの（wordfreq の段で基本形か連用形が身近）が1つに決まれば直す、並べば紫。
名詞の読みに動詞の連用形が無ければ（お茶します）何もしない。特定の語や文字列には合わせない。
"""
import difflib

COMMON = 470     # 直し先の動詞の wordfreq の段（基本形か連用形の身近なほう・大きいほど珍しい）
CLEAR = 60       # 2番手の動詞よりこれだけ身近なら1つに決める
_SURU = ('する', '致す', 'いたす')


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _stem_candidates(reading, noun):
    """読みが reading の動詞の連用形（ます が続く形）の表記と基本形。"""
    import reading_lattice
    from morphology import tokenize
    reading_lattice.load()
    out = {}
    for surf, _l, _r, _c, pos in reading_lattice._table.get(reading, ()):
        if pos != '動詞' or surf == noun or surf in out:
            continue
        toks = list(tokenize(surf + 'ます'))
        if len(toks) != 2 or toks[0].surface != surf or toks[0].pos != '動詞':
            continue
        if getattr(toks[0], 'pos_sub', '') != '自立' or not str(getattr(toks[0], 'infl_form', '連用形')).startswith('連用'):
            continue
        if _hira(toks[0].reading) != reading:
            continue
        out[surf] = getattr(toks[0], 'base_form', '') or surf
    return out


def propose(text):
    """[(開始, 終了, 置く表記 or None)]。"""
    from morphology import tokenize
    import ime_reconvert
    toks = list(tokenize(text))
    marks = []
    for i, t in enumerate(toks):
        # お＋名詞 が1語か、接頭詞 お＋名詞 の2語
        if t.surface.startswith('お') and len(t.surface) > 1 and t.pos == '名詞':
            noun, start, nxt = t.surface[1:], t.start + 1, i + 1
            reading = _hira(t.reading)[1:] if t.has_reading and _hira(t.reading).startswith('お') else None
            sub = getattr(t, 'pos_sub', '')
        elif t.surface == 'お' and t.pos == '接頭詞' and i + 1 < len(toks) and toks[i + 1].pos == '名詞':
            n = toks[i + 1]
            noun, start, nxt = n.surface, n.start, i + 2
            reading = _hira(n.reading) if n.has_reading else None
            sub = getattr(n, 'pos_sub', '')
        else:
            continue
        if not reading or sub != '一般' or nxt >= len(toks):
            continue
        after = toks[nxt]
        if after.pos != '動詞' or (getattr(after, 'base_form', '') or after.surface) not in _SURU:
            continue
        cands = _stem_candidates(reading, noun)
        ranked = sorted((min(ime_reconvert._rank(base), ime_reconvert._rank(surf)), surf) for surf, base in cands.items())
        ranked = [x for x in ranked if x[0] <= COMMON]
        if not ranked:
            continue
        end = start + len(noun)
        # 元の名詞のほうが身近なら（お酒します）決めずに紫
        clear = len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= CLEAR
        if clear and ime_reconvert._rank(noun) > ranked[0][0]:
            marks.append((start, end, ranked[0][1]))
        else:
            marks.append((start, end, None))
    return marks


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
    new = done
    odd_add, details = [], []
    for s, e, rep in sorted(marks, reverse=True):
        if any(x < e and s < y for x, y in changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        if rep:
            new = new[:s] + rep + new[e:]
            details.append([done[s:e], rep, 'お＋動詞＋する'])
        elif not any(x < org[1] and org[0] < y for x, y in odd_now):
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if odd_add:
        out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, f'「お{line[a:b]}する」の「{line[a:b]}」は、同じ読みの動詞（お〜する の形）かもしれません')
            for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
