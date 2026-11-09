# -*- coding: utf-8 -*-
"""IME が「名詞＋です／ます」の読みを片仮名の1語（固有名詞）にした所を戻す段（kata_copula・2026-11-08 手分けA）。

かいとうあんです を IME が 怪盗｜アンデス にすることがある（あんです → アンデス: 案＋です を片仮名の地名1語にした）。
打った記録の在る所で、片仮名の語（表に無いか珍しい語・固有名詞）の読みが です・でした・ます・ました で終わり、
前の残り（あん）が身近な名詞の読みなら、名詞＋です に戻す。すぐ前の漢字の名詞が同じ打った文節なら、その名詞も
同じ読みの表記から選び直す（怪盗／回答 は 回答案です の方が行の費用＋身近さがよい）。一番よい形が、2番目より
はっきりよいときだけ直し、そうでなければ紫。記録の無い行（貼り付け・前に書いた片仮名の語）は何もしない。
特定の語や文字列には合わせない。

ime_reconvert.repair_line の最後から呼ぶ。切り替え: CN_KATA_COPULA=0 で何もしない。
"""
import difflib
import os
from functools import lru_cache

ENDINGS = ('でした', 'です', 'ました', 'ます')
RARE = 560
NOUN_COMMON = 470
RANK_W = 40
MARGIN = 1500
SUFFIX_MIN = 5


def _on():
    return os.environ.get('CN_KATA_COPULA') != '0'


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in s)


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


@lru_cache(maxsize=256)
def _suffix_count(h):
    """JMdict の名詞の表で、漢字2字＋h の3字の語の数（h が名詞に付く接尾としてどれだけ使われるか）。"""
    try:
        import context_skeleton
        jm = context_skeleton._jm_nouns()
    except Exception:
        return 0
    return sum(1 for w in jm if len(w) == 3 and w[2] == h and _kanji(w[0]) and _kanji(w[1]))


def propose(text):
    """[(開始, 終了, 置く行 or None)]。"""
    if not _on() or not text:
        return []
    try:
        import ime_reconvert as R
        from morphology import tokenize, path_cost, dictionary_base_pos
    except Exception:
        return []
    tokens = list(tokenize(text))
    if not any(_kata(t.surface) for t in tokens):
        return []
    rw = R.typed_reverse(text, tokens, None)
    if not rw:
        return []
    phon, words = rw

    def noun(f):
        return any(p.startswith('名詞,一般') or p.startswith('名詞,サ変接続') or p.startswith('名詞,形容動詞語幹')
                   for p in (dictionary_base_pos(f) or ()))

    def score(line, a, b):
        c = path_cost(line)
        if c is None:
            return None
        rk = sum(R._rank(t.surface) for t in tokenize(line)
                 if t.start < b and a < t.end and (any(_kanji(x) for x in t.surface) or _kata(t.surface)))
        return c + RANK_W * rk
    out = []
    for i, t in enumerate(tokens):
        if not _kata(t.surface) or len(t.surface) < 3:
            continue
        if R._rank(t.surface) < RARE and not (t.pos_sub or '').startswith('固有名詞'):
            continue
        # 打った記録の文節の中の語だけ
        w = [x for x in words if x[0] <= t.start and t.end <= x[1] and x[5] == 'typed']
        norec = False
        if not w:
            # 行に打った記録が1つも無い（開き直した行・diag）。片仮名の読みは字のとおりなので、すぐ前の漢字の名詞と
            # 組で選び直せるときだけ見る（2026-11-08 手分けB）。CN_KATA_COPULA_NOREC=0 で前のまま（何もしない）
            if os.environ.get('CN_KATA_COPULA_NOREC') == '0' or any(x[5] == 'typed' for x in words):
                continue
            norec = True
        rd = _hira(t.surface)
        end = next((x for x in ENDINGS if rd.endswith(x) and len(rd) > len(x)), None)
        if end is None:
            continue
        # 後ろは行の終わり・記号・助詞だけ（片仮名の語の後ろにさらに です が続く行は、片仮名の語を書いた行）
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if nxt is not None and nxt.pos not in ('記号', '助詞'):
            continue
        rest = rd[:-len(end)]
        heads = [f for f in R._dict_faces(rest) if noun(f) and R._rank(f) <= NOUN_COMMON and not _kata(f)]
        if not heads:
            continue
        # すぐ前の漢字の名詞（同じ打った文節か、すぐ前の打った文節）は同じ読みの表記から選び直す
        s, e = t.start, t.end
        prevs = ['']
        p = tokens[i - 1] if i > 0 else None
        if p is not None and p.end == t.start and p.pos == '名詞' and all(_kanji(c) for c in p.surface) \
                and (norec or w[0][0] <= p.start
                     or any(x[0] <= p.start and x[1] == w[0][0] and x[5] == 'typed' for x in words)):
            prd = R._record_reading(text, p.start, p.end, R._active_record()) or _hira(p.reading or '')
            if prd:
                prevs = [x for x in dict.fromkeys([p.surface] + list(R._dict_faces(prd)))
                         if all(_kanji(c) for c in x) and noun(x)]
                s = p.start
        if norec and s == t.start:
            continue                     # 記録が無ければ、前の名詞と組にできる所だけ
        # 1字の名詞が幾つか在るなら、漢字2字の名詞に付く接尾として語の表によく在る1つだけ（〜案 は多い、〜安・〜庵 は少ない）
        one = [h for h in heads if len(h) == 1]
        if len(one) > 1:
            cnt = sorted(((_suffix_count(h), h) for h in one), reverse=True)
            keep = cnt[0][1] if cnt[0][0] >= SUFFIX_MIN and cnt[0][0] >= 2 * cnt[1][0] else None
            heads = [h for h in heads if len(h) > 1 or h == keep]
        here = score(text, s, e)
        cands = []
        for pv in prevs:
            for h in heads:
                face = pv + h + end
                line = text[:s] + face + text[e:]
                if len(h) == 1:
                    # 1字の名詞は、前の名詞に付く接尾の名詞として読める形だけ（回答＋案）。前に名詞が無ければ見ない
                    if not pv:
                        continue
                    ht = [x for x in tokenize(line) if x.start == s + len(pv) and x.end == s + len(pv) + 1]
                    if not ht or ht[0].pos != '名詞' or not (ht[0].pos_sub or '').startswith('接尾'):
                        continue
                sc = score(line, s, s + len(face))
                if sc is not None and (here is None or sc < here):
                    cands.append((sc, line))
        if not cands:
            continue
        cands.sort()
        if len(cands) == 1 or cands[1][0] - cands[0][0] >= MARGIN:
            out.append((s, e, cands[0][1]))
        else:
            out.append((t.start, t.end, None))
    return out


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
    out = dict(result)
    new, details, odd_add, fixed = done, [], [], None
    for s, e, other in marks:
        if overlaps(s, e, changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or overlaps(org[0], org[1], list(decided or ())):
            continue
        if other and fixed is None:
            sops = [o for o in difflib.SequenceMatcher(None, done, other, autojunk=False).get_opcodes() if o[0] != 'equal']
            new = done[:sops[0][1]] + other[sops[0][3]:sops[-1][4]] + done[sops[-1][2]:]
            details.append([done[sops[0][1]:sops[-1][2]], other[sops[0][3]:sops[-1][4]], 'IMEの選び違い'])
            fixed = (s, e)
        elif other is None:
            odd_add.append((s, e))
    if new == done and not odd_add:
        return result
    if fixed:
        d = len(new) - len(done)
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [((x[0] + d, x[1] + d) if x[0] >= fixed[1] else (x[0], x[1])) + tuple(x[2:])
                            for x in out[key] if not (x[0] < fixed[1] and fixed[0] < x[1])]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [((r[0] + d, r[1] + d) if r[0] >= fixed[1] else (r[0], r[1])) + tuple(r[2:])
                                  for r in out['odd_reasons'] if not (r[0] < fixed[1] and fixed[0] < r[1])]
    if odd_add:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, f'「{done[a:b]}」は「名詞＋です」を片仮名の1語に変換したものかもしれません') for a, b in odd_add]
    if new != done:
        lops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
    return out
