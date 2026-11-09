# -*- coding: utf-8 -*-
"""漢字の語＋助詞＋片仮名の語 で、漢字の語の読みの最後の字と助詞が入れ替わった打ち違い（みぎ｜で｜だぶる… を
みぎ｜だ｜で｜ぶる… と打ち、右田｜で｜ブルクリック になった形）を戻す（2026-11-09 手分けA）。

- 見る所: 漢字の名詞 W ＋ 1字の格助詞 P ＋ 片仮名の並び K で、K の頭の語が一般の名詞でない（人名・地名などの
  固有名詞か未知の語）。片仮名の知らない語の頭は、前の字を取り込み損ねた切れ端のことがある。
- 候補: W の読みの最後の字 m（゛゜ を付け外しした字も）を K の頭へ移す。W は残りの読み（みぎ）の身近な表記、
  K は m＋K の片仮名（ダブルクリック）で、どの語も一般の名詞として読めること。
- 行の並びの費用（morphology.path_cost）が GAIN 以上下がる候補が1つなら直す。2つ以上なら紫。
打った記録も IME も使わない（読みは辞書の読み）。特定の語には合わせない。CN_KATA_HEAD_SWAP=0 で見ない。
"""
import difflib
import os

GAIN = 3000
COMMON = 470
_PARTICLES = frozenset('でにをがとへもは')
_VOICE = {}
for a, b in zip('かきくけこさしすせそたちつてとはひふへほ', 'がぎぐげござじずぜぞだぢづでどばびぶべぼ'):
    _VOICE[a] = b
    _VOICE[b] = a
for a, b in zip('はひふへほ', 'ぱぴぷぺぽ'):
    _VOICE.setdefault(b, a)


def _on():
    return os.environ.get('CN_KATA_HEAD_SWAP') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in s)


def _to_kata(s):
    return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in s)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _general_noun(t):
    sub = t.pos_sub or ''
    return t.pos == '名詞' and not sub.startswith(('固有名詞', '非自立', '代名詞', '数', '接尾')) and t.has_reading


def propose(text):
    import morphology
    import ime_reconvert as R
    toks = list(morphology.tokenize(text))
    out = []
    for i in range(len(toks) - 2):
        w, p = toks[i], toks[i + 1]
        if not (w.pos == '名詞' and all(_kanji(c) for c in w.surface) and w.has_reading):
            continue
        if p.surface not in _PARTICLES or p.pos != '助詞' or w.end != p.start:
            continue
        j = i + 2
        while j < len(toks) and _kata(toks[j].surface) and toks[j].start == toks[j - 1].end:
            j += 1
        ks = toks[i + 2:j]
        if not ks or ks[0].start != p.end or _general_noun(ks[0]):
            continue
        k_end = ks[-1].end
        rd = _hira(w.reading)
        if len(rd) < 3:
            continue
        here = morphology.path_cost(text)
        if here is None:
            continue
        found = {}
        for m in {rd[-1], _VOICE.get(rd[-1], rd[-1])}:
            faces = [f for f in R._dict_faces(rd[:-1]) if R._rank(f) <= COMMON and any(_kanji(c) for c in f)]
            if not faces:
                continue
            kk = _to_kata(m) + text[p.end:k_end]
            new_k = list(morphology.tokenize(kk))
            if not new_k or not all(_general_noun(t) for t in new_k):
                continue
            for f in faces[:1]:
                cand = text[:w.start] + f + p.surface + kk + text[k_end:]
                c = morphology.path_cost(cand)
                if c is not None and c <= here - GAIN:
                    found[cand] = c
        if found:
            out.append((w.start, k_end, next(iter(found)) if len(found) == 1 else None))
    return out


def repair_line(line, result, decided=()):
    if not _on() or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done != line:
        return result          # 直した行では見ない（位置を合わせない）
    try:
        marks = propose(done)
    except Exception:
        return result
    if not marks:
        return result
    for s, e, cand in marks:
        if any(x < e and s < y for x, y in list(decided or ())):
            continue
        out = dict(result)
        if cand is None:
            now = [tuple(x[:2]) for x in out.get('odd_spans') or ()]
            out['odd_spans'] = sorted(set(now) | {(s, e)})
            out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
                (s, e, '助詞の前後の字が入れ替わった打ち違いかもしれません')]
            return out
        lops = [o for o in difflib.SequenceMatcher(None, line, cand, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': cand, 'changed': True,
                    'details': list(result.get('details') or []) + [[line[s:e], cand[s:e + len(cand) - len(line)], '打ち違い']],
                    'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
        out['odd_spans'] = [x for x in out.get('odd_spans') or () if x[1] <= s or e <= x[0]]
        return out
    return result
