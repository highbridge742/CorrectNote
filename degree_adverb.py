# -*- coding: utf-8 -*-
"""程度の副詞が、受ける述語の無い名詞にかかっている所（2026-10-26・うにさん「正しいと思います。それで進めて」）。

    とても思い → とても重い（思い は名詞・同じ読みの形容詞 重い がある）

程度の副詞（分類語彙表 3.1920「程度」の語・degree_adverbs.json）は、様子や度合いを表す語（形容詞・動詞・形容動詞）に
かかる。名詞に直接かかって、その名詞を受ける述語も無い（行末・句読点・だ／です の前）なら、文が成り立たない。
「とても思いが強い」は とても が 強い にかかるので見ない（名詞の後ろに助詞が続く形は見ない）。

直し: 漢字で書いた名詞（または行末・句点の前の動詞の連用形）と同じ読みの形容詞が辞書に在れば、それに置く。
候補が複数なら身近さの表（everyday_faces）の先頭で決める。決まらない・候補が無い名詞は紫。
時・場所・量の名詞（ちょっと前・かなり昔・少し水 の類: 分類語彙表 1.16／1.17／1.19 や副詞可能・数）は見ない。
かなで書いた語（とてもおもい）は形容詞にも読めるので触らない。語を名指しした表は持たない。
"""
import difflib
import json
import os
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
_END = '。！!？?'


@lru_cache(maxsize=1)
def degree_words():
    try:
        with open(os.path.join(_HERE, 'degree_adverbs.json'), encoding='utf-8') as f:
            return frozenset(json.load(f)['words'])
    except Exception:
        return frozenset()


def _kanji_any(s):
    return any('一' <= c <= '鿿' or c == '々' for c in s)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _adverb_end(toks, i, words):
    """toks[i] から始まる程度の副詞の終わりの添字（無ければ None）。とても・非常に・すごく の形。"""
    t = toks[i]
    if t.surface in words and t.pos == '副詞':
        return i + 1
    # 形容動詞の語幹＋に（非常に・大変に）・語幹だけ（大変）
    if t.surface in words and t.pos == '名詞' and t.pos_sub == '形容動詞語幹':
        if i + 1 < len(toks) and toks[i + 1].surface == 'に' and toks[i + 1].start == t.end:
            return i + 2
        return i + 1
    # 形容詞の連用形（すごく・ひどく・えらく）: 程度の語に原形か連用形が在るもの
    if t.pos == '形容詞' and (getattr(t, 'infl_form', '') or '').startswith('連用'):
        base = getattr(t, 'base_form', '') or ''
        if t.surface in words or base in words:
            return i + 1
    return None


def _quantity_like(tok):
    """時・場所・量の名詞（程度の副詞が普通にかかる: ちょっと前・かなり昔・少し水）。"""
    if tok.pos_sub in ('副詞可能', '数', '接尾', '代名詞', '固有名詞', '非自立'):
        return True
    try:
        import semantic_class
        codes = semantic_class.codes(tok.surface) or ()
    except Exception:
        codes = ()
    return any(str(c).startswith(('1.16', '1.17', '1.19')) for c in codes)


def _no_predicate_after(toks, j, text):
    """toks[j] の後ろに、その語を受ける述語が無い（行末・句点・だ／です）。"""
    end = toks[j].end
    if end >= len(text):
        return True
    if text[end] in _END:
        return True
    # 名詞は な を挟まずに ので・のに・けど を受けない（思いので）。これも受ける述語の無い形
    if any(text.startswith(x, end) for x in ('ので', 'のに', 'けど', 'けれど')):
        return True
    nxt = toks[j + 1] if j + 1 < len(toks) else None
    if nxt is not None and nxt.start == end and nxt.pos == '助動詞' and nxt.surface in ('だ', 'です', 'でした', 'だった'):
        rest = nxt.end
        return rest >= len(text) or text[rest] in _END
    return False


def _adjective_faces(reading, dict_index):
    """同じ読みの形容詞（基本形）の表記。"""
    from morphology import tokenize
    faces = []
    seen = set()
    pools = []
    try:
        pools.append(dict_index.inflected_surfaces_for_reading(reading) or ())
    except Exception:
        pass
    try:
        pools.append(dict_index.surfaces_for_reading(reading) or ())
    except Exception:
        pass
    for pool in pools:
        for f in pool:
            f = f if isinstance(f, str) else (f[0] if f else '')
            if not f or f in seen or not _kanji_any(f):
                continue
            seen.add(f)
            t = tokenize(f)
            if len(t) == 1 and t[0].pos == '形容詞' and (getattr(t[0], 'infl_form', '') or '') == '基本形' \
                    and _hira(t[0].reading or '') == reading:
                faces.append(f)
    return faces


def propose(text, dict_index):
    """[(開始, 終了, 置く表記 or None)]。None は紫だけ。"""
    words = degree_words()
    if not words or not text or not _kanji_any(text):
        return []
    from morphology import tokenize
    toks = tokenize(text)
    out = []
    for i in range(len(toks)):
        k = _adverb_end(toks, i, words)
        if k is None or k >= len(toks):
            continue
        t = toks[k]
        if t.start != toks[k - 1].end or not _kanji_any(t.surface) or not t.has_reading:
            continue
        # サ変の名詞（賛成・感謝）は する を省いた述語として程度の副詞を受ける（おおむね賛成だ）ので見ない
        is_noun = t.pos == '名詞' and t.pos_sub == '一般'
        is_renyou = t.pos == '動詞' and (getattr(t, 'infl_form', '') or '').startswith('連用')
        if not (is_noun or is_renyou) or _quantity_like(t):
            continue
        if not _no_predicate_after(toks, k, text):
            continue
        reading = _hira(t.reading or '')
        faces = _adjective_faces(reading, dict_index)
        if len(faces) > 1:
            try:
                import everyday_faces
                order, _dom = everyday_faces.order(reading)
                pick = [f for f in order if f in faces]
                faces = pick[:1] if pick else faces
            except Exception:
                pass
        if len(faces) == 1:
            out.append((t.start, t.end, faces[0]))
        elif is_noun:
            out.append((t.start, t.end, None))
    return out


def _to_original(line, done, s, e):
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= s and e <= i2:
            return s - i1 + j1, e - i1 + j1
    return None


def repair_line(line, result, dict_index, decided=()):
    """result: ほかの補正の答え。ほかの補正が触っていない所だけ見る。"""
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, dict_index)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    odd_add, details = [], []
    for s, e, face in sorted(marks, key=lambda m: m[0], reverse=True):
        if any(x < e and s < y for x, y in changed):
            continue
        org = _to_original(line, done, s, e)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(odd_now) + list(decided or ())):
            continue
        if face:
            new = new[:s] + face + new[e:]
            details.append([done[s:e], face, '程度の副詞'])
        else:
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if odd_add:
        out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」は程度の副詞を受ける語ではありません') for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
