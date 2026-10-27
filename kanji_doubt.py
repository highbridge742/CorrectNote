# -*- coding: utf-8 -*-
"""常用漢字表の外の字を含む語を「疑う」段（2026-10-26・うにさん）。

うに 10-26 10:17Z「常用漢字表でよい。いきなり紫をつけるのではなく、一度は疑い、直前の2文字からの予測や、一般的な
ミスタイプに当てはめてより自然な文ができるようなら、紫や補正を実行する段階でチェックする。人名とさんの組み合わせ
根拠が見える場合もスルーで問題ない」

段:
1. 疑う: 語（janome の1語）に常用漢字表（joyo_kanji.json・2136字）の外の字が1字でもあり、本人の語彙に無く、
   後ろに 人名・地名の印（さん・氏・様・君・市・町…）が付かない。疑うだけでは何も付けない。
2. 当てはめる: その語の読みに一般のミスタイプ（contextual_repair.key_repairs: 同じ読み＝IME の選び違い・隣のキー・
   巻き込み・抜け・二度押し・入れ替わり）を当て、届く読みの語のうち常用漢字だけで書ける表記を候補にする。
3. 比べる: 候補は身近な語（kango_tier 層1・2／身近さの表の先頭）で、後ろの 助詞＋述語 の組の意味の仲間に入る
   （semantic_class・区間を食べる は採らない）もの。直前の字を含む行ぜんたいの自然さ（naturalness.gain_in_line）が
   元より悪くならない候補が在れば紫、候補が1つで自然さが MIN_GAIN_READABLE 以上上がるなら直す。
   常用外でも kango_tier 層1 の語（鞄）は疑わない。
"""
import difflib
import json
import os
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
DOUBT_GAIN = 0
_NAME_MARKS = ('さん', 'ちゃん', 'くん', '君', '氏', '様', 'さま', '先生', '殿', '選手', '社長', '部長', '課長',
               '市', '町', '村', '県', '区', '郡', '駅', '線', '川', '山', '島', '通り')
MAX_FACES = 12


@lru_cache(maxsize=1)
def joyo():
    try:
        with open(os.path.join(_HERE, 'joyo_kanji.json'), encoding='utf-8') as f:
            return frozenset(json.load(f)['chars'])
    except Exception:
        return frozenset()


def _kanji(c):
    return '一' <= c <= '鿿'


def outside(surface):
    j = joyo()
    return bool(j) and any(_kanji(c) and c not in j for c in surface)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def suspects(text, store=None):
    """[(開始, 終了, 読み)]: 疑う語と、その語を左右の語（直前の語・直後の語）とつないだ窓。
    1字の語（鵜・李）は読みが短く、打ち違いを戻しても語に届きにくいので、IME の文節に当たる隣の語ともつなぐ。"""
    from morphology import tokenize
    if not joyo():
        return []
    out = []
    toks = tokenize(text)
    for i, t in enumerate(toks):
        if not outside(t.surface) or not t.has_reading:
            continue
        after = text[t.end:]
        if t.pos_sub == '固有名詞' or any(after.startswith(m) for m in _NAME_MARKS):
            continue
        # 常用外でも、ふだん使う語と判定された語（鞄: kango_tier 層1）は疑わない
        try:
            import kango_tier
            if kango_tier.known_usage_tier(t.surface) == 1:
                continue
        except Exception:
            pass
        if store is not None:
            try:
                if any(e.get('surface') == t.surface for e in store.lookup(_hira(t.reading))):
                    continue
            except Exception:
                pass
        out.append((t.start, t.end, _hira(t.reading)))
        for a, b in ((i - 1, i), (i, i + 1), (i - 1, i + 1)):
            if a < 0 or b >= len(toks):
                continue
            part = toks[a:b + 1]
            if any(p.end != q.start for p, q in zip(part, part[1:])) or not all(p.has_reading for p in part):
                continue
            if any(p.pos in ('記号', '助動詞') for p in part):
                continue
            out.append((part[0].start, part[-1].end, ''.join(_hira(p.reading) for p in part)))
    return out


def _faces(reading, store, dict_index):
    seen = []
    try:
        for e in store.lookup(reading) or ():
            seen.append(e.get('surface'))
    except Exception:
        pass
    try:
        seen.extend(f if isinstance(f, str) else f[0] for f in (dict_index.surfaces_for_reading(reading) or ()))
    except Exception:
        pass
    out = []
    for f in seen:
        if f and f not in out and not outside(f) and any(_kanji(c) for c in f):
            out.append(f)
    return out[:MAX_FACES]


def _common(face, reading):
    """候補の表記が身近な語か（kango_tier の層1・2、身近さの表の先頭、本人の語彙）。"""
    try:
        import kango_tier
        t = kango_tier.known_usage_tier(face)
        if t is not None and t <= 2:
            return True
    except Exception:
        pass
    try:
        import everyday_faces
        faces, _d = everyday_faces.order(reading)
        if faces and faces[0] == face:
            return True
    except Exception:
        pass
    return False


def _frames(text):
    """{語の終わり: (助詞, 述語の基本形)}: 語のすぐ後ろが格助詞で、その次が動詞のもの。"""
    from morphology import tokenize
    toks = tokenize(text)
    out = {}
    for i in range(len(toks) - 2):
        a, b, c = toks[i], toks[i + 1], toks[i + 2]
        if b.pos == '助詞' and b.start == a.end and c.pos == '動詞' and c.start == b.end:
            out[a.end] = (b.surface, getattr(c, 'base_form', '') or c.surface)
    return out


def _fits_frame(face, frame):
    """候補が 助詞＋述語 の組の意味の仲間か。組の表に無い組（分類が引けない）は判断しない（True）。"""
    try:
        import semantic_class
        p, v = frame
        if not semantic_class.pv_classes(p, v) or not semantic_class.codes(face):
            return True
        return semantic_class._shares(face, p, v)
    except Exception:
        return True


def propose(text, store, dict_index):
    """[(開始, 終了, 置く表記 or None)]。

    疑った語の読みに一般のミスタイプを当てて届く表記のうち、身近な語（_common）で、後ろの 助詞＋述語 の組の
    意味の仲間に入り、行の自然さが元より DOUBT_GAIN 以上（悪くならない）ものを候補にする。候補が1つでも在れば
    疑いは確かになる（紫）。候補が1つで、行の自然さが MIN_GAIN_READABLE 以上上がるなら直す。
    """
    from contextual_repair import key_repairs
    import naturalness as N
    best_by_core = {}
    frames = _frames(text)
    for s, e, rd in suspects(text, store):
        frame = frames.get(e)
        try:
            reps = key_repairs(rd, text[:s][-1:], text[e:][:1])
        except Exception:
            continue
        cands = {}
        for r in reps:
            r = getattr(r, 'reading', r)
            for f in _faces(r, store, dict_index):
                if f == text[s:e] or f in cands or not _common(f, r):
                    continue
                # 後ろの 助詞＋述語 の組（区間を食べる）に意味の仲間として入らない候補は採らない（直前直後の文脈で予測）
                if frame and not _fits_frame(f, frame):
                    continue
                g = N.gain_in_line(text, s, e, f)
                if g is not None and g >= DOUBT_GAIN:
                    cands[f] = g
        if not cands:
            continue
        ranked = sorted(cands.items(), key=lambda x: -x[1])
        best, g = ranked[0]
        face = best if (len(ranked) == 1 and g >= N.MIN_GAIN_READABLE) else None
        key = next((k for k in best_by_core if k[0] < e and s < k[1]), None)
        if key is None:
            best_by_core[(s, e)] = (g, face)
        elif g > best_by_core[key][0]:
            del best_by_core[key]
            best_by_core[(s, e)] = (g, face)
    return [(s, e, face) for (s, e), (g, face) in best_by_core.items()]


def repair_line(line, result, store, dict_index, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, store, dict_index)
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
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(odd_now) + list(decided or ())):
            continue
        if face:
            new = new[:s] + face + new[e:]
            details.append([done[s:e], face, '常用外の字'])
        else:
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if odd_add:
        out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」は常用漢字の外の字で、打ち違いを戻すとより自然な文になります') for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
