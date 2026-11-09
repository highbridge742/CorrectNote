# -*- coding: utf-8 -*-
"""巻き込みの1打で崩れた名詞の句を戻す段（rollin_word・2026-11-08 手分け・うにさん「手分けできるなら手分けして」）。

かな入力で、あるキーを打つときに隣のキーも一緒に押すと、読みに余分な1字が入る（でんきだい → でんなきだい：
ん の隣の な）。IME はその読みを変換できず、かなの切れ端（でん｜なき｜だい）や、珍しい語（でん｜鳴き｜代・
でん｜な｜稀代）になる。

句（助詞・記号で区切った語の並び）の読みに、前後どちらかの字と隣り合うキーの字が1つ入っているとき、その字を
抜いた読みが、身近な名詞（＋接尾の名詞: 代・費・料 など）にきれいに組めて、行の費用がはっきり下がるなら直す。
組める形が2つ以上で差が無ければ紫にとどめる。特定の語や文字列には合わせない。

句の漢字の語の読みは、打った記録が在ればそれ（ime_reconvert._record_reading）、無ければ辞書の読みと、その読みの
1字の濁り（きたい／きだい）を替えたもの。

切り替え: CN_ROLLIN_WORD=0 で何もしない（前のまま）。
"""
import os
from functools import lru_cache

RARE = 560          # 句の中にこれ以上珍しい語（表に無いかなの切れ端は 800）があるときだけ疑う
HEAD_COMMON = 470   # 直した先の名詞の身近さ
TAIL_COMMON = 450   # 接尾の名詞の身近さ
GAIN = 1500         # 行の費用がこれだけ下がれば候補
FIX_MARGIN = 800    # 2番目の候補との差がこれ以上なら直す（足りなければ紫）
KEY_NEAR = 1.05     # 隣のキーとみる距離（kana_layout.kana_key_distance の intrusion）
MAX_TOKENS = 5
RANK_W = 40         # 表記の選び: 語の身近さ（珍しさの和）1あたりの行の費用（同じ読みの 代／台／帯 は身近な方）

_SMALL = 'ゃゅょぁぃぅぇぉっー'
_VOICE = {a: b for a, b in zip('かきくけこさしすせそたちつてとはひふへほ',
                               'がぎぐげござじずぜぞだぢづでどばびぶべぼ')}
_UNVOICE = {b: a for a, b in _VOICE.items()}


def _on():
    return os.environ.get('CN_ROLLIN_WORD') != '0'


def _kanji(c):
    return '一' <= c <= '鿿'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _is_hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in s)


def _rank(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face)
    except Exception:
        return 800


@lru_cache(maxsize=4096)
def _pos(face):
    try:
        from morphology import dictionary_base_pos
        return frozenset(dictionary_base_pos(face) or ())
    except Exception:
        return frozenset()


def _is_suffix(face):
    return any(p.startswith('名詞,接尾,一般') for p in _pos(face))


def _is_plain_noun(face):
    return any(p.startswith('名詞,一般') or p.startswith('名詞,サ変接続') or p.startswith('名詞,形容動詞語幹')
               for p in _pos(face))


@lru_cache(maxsize=8192)
def _faces(reading):
    try:
        import ime_reconvert
        return ime_reconvert._dict_faces(reading, 12)
    except Exception:
        return ()


@lru_cache(maxsize=8192)
def _unit(face):
    try:
        import seed_japanese
        return seed_japanese.is_unit(face) is True
    except Exception:
        return False


def _near(a, b):
    try:
        import kana_layout
        return kana_layout.kana_key_distance(a, b, intrusion=True) <= KEY_NEAR
    except Exception:
        return False


def _token_readings(text, t, tokens):
    """語の読みの候補（打った記録が在ればそれだけ）。"""
    surf = t.surface
    if _is_hira(surf):
        return [surf]
    if all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surf):
        return [_hira(surf)]
    try:
        import ime_reconvert
        rec = ime_reconvert._record_reading(text, t.start, t.end, ime_reconvert._active_record())
    except Exception:
        rec = None
    if rec:
        return [rec]
    out = []
    base = _hira(t.reading or '')
    if base and _is_hira(base):
        out.append(base)
    try:
        from inflected_lexicon import dictionary_readings
        out.extend(_hira(r) for r in dictionary_readings(surf) or ())
    except Exception:
        pass
    # 複合語の後ろの語の頭の濁り（き｜たい／き｜だい）は辞書に無いことがある: 2字目以降の1字の濁りを替える
    more = []
    for r in out:
        for i in range(1, len(r)):
            c = r[i]
            alt = _VOICE.get(c) or _UNVOICE.get(c)
            if alt:
                more.append(r[:i] + alt + r[i + 1:])
    return list(dict.fromkeys([r for r in out + more if _is_hira(r)]))[:6]


def _segments(tokens):
    """助詞・記号で区切った語の並び [(開始の語, 終わりの語+1)]。"""
    out, i = [], 0
    n = len(tokens)
    while i < n:
        if tokens[i].pos in ('助詞', '記号'):
            i += 1
            continue
        j = i
        while j < n and tokens[j].pos not in ('助詞', '記号'):
            j += 1
        # 句の終わりの助動詞（た・です）は句に入れない
        k = j
        while k > i + 1 and tokens[k - 1].pos == '助動詞':
            k -= 1
        out.append((i, k))
        i = j
    return out


def _doubt(seg):
    """句の語ごとに、巻き込みの字が入っていると疑える語か（[bool]）。疑える語が無ければ None。
    漢字を含む語はめったに使わない語（RARE 以上）だけ。かなの語は、句が漢字の珍しい語を含むか、句がかなだけのとき。
    身近な漢字の語（会議・男・人）の中の字は抜かない。"""
    if len(seg) < 2 or len(seg) > MAX_TOKENS:
        return None
    # 動詞を含む句（かっ｜と｜し・し｜て｜た｜ん）は活用の並びで、名詞の崩れではない
    if any(t.pos == '動詞' for t in seg):
        return None
    rare = [any(_kanji(c) for c in t.surface) and _rank(t.surface) >= RARE for t in seg]
    all_kana = all(_is_hira(t.surface) for t in seg)
    if not any(rare) and not all_kana:
        return None
    whole = ''.join(t.surface for t in seg)
    if _unit(whole):
        return None
    return [r or _is_hira(t.surface) for r, t in zip(rare, seg)]


def _drops(reading, ok=None):
    """隣のキーの巻き込みで入った1字を抜いた読み。ok: 読みの字ごとに抜いてよいか。"""
    out = []
    # 前の字のキーを押すときに隣のキーも押した形（ん＋な）。句の頭の字は抜かない（お｜かわり の お は接頭）
    for i, c in enumerate(reading):
        if i == 0 or c in _SMALL or len(reading) < 4 or (ok is not None and not ok[i]):
            continue
        if reading[i - 1] != c and _near(reading[i - 1], c):   # 同じ字の2度押しは別の型
            out.append(reading[:i] + reading[i + 1:])
    return list(dict.fromkeys(out))


def _build(reading):
    """読みを身近な名詞1つ、または 身近な名詞＋接尾の名詞 に組んだ表記 [(表記, 珍しさ)]。"""
    out = []
    for f in _faces(reading):
        if any('ァ' <= c <= 'ヶ' for c in f):
            continue                      # 元に無い片仮名は持ち込まない
        if len(f) >= 2 and _is_plain_noun(f) and _rank(f) <= HEAD_COMMON:
            out.append((f, 2 * _rank(f)))
    for k in range(2, len(reading)):
        head, tail = reading[:k], reading[k:]
        if len(tail) > 3:
            continue
        heads = [f for f in _faces(head) if len(f) >= 2 and _is_plain_noun(f) and _rank(f) <= HEAD_COMMON]
        tails = [f for f in _faces(tail) if len(f) == 1 and _kanji(f) and _is_suffix(f) and _rank(f) <= TAIL_COMMON]
        if not heads or not tails:
            continue
        # 名詞＋接尾の組は、語の表（seed_japanese）に1語として在るものだけ（電気代 は在る・電気帯 は無い）
        for hh in heads:
            for t in tails:
                if _unit(hh + t):
                    out.append((hh + t, _rank(hh) + _rank(t)))
    return out


def propose(text):
    """[(開始, 終了, 置く表記 or None)]。"""
    if not _on() or not text:
        return []
    from morphology import tokenize, path_cost
    tokens = list(tokenize(text))
    here = path_cost(text)
    if here is None:
        return []
    found = []
    for a, b in _segments(tokens):
        seg = tokens[a:b]
        doubt = _doubt(seg)
        if doubt is None:
            continue
        s, e = seg[0].start, seg[-1].end
        readings = [('', ())]
        for t, d in zip(seg, doubt):
            readings = [(x + y, m + (d,) * len(y)) for x, m in readings
                        for y in _token_readings(text, t, tokens)][:24]
        cands = {}
        for r, mask in readings:
            for r2 in _drops(r, mask):
                for face, rk in _build(r2):
                    if face == text[s:e]:
                        continue
                    line = text[:s] + face + text[e:]
                    c = path_cost(line)
                    if c is None or here - c < GAIN:
                        continue
                    sc = c + RANK_W * rk
                    if face not in cands or sc < cands[face]:
                        cands[face] = sc
        if not cands:
            continue
        ranked = sorted(cands.items(), key=lambda x: x[1])
        if len(ranked) == 1 or ranked[1][1] - ranked[0][1] >= FIX_MARGIN:
            found.append((s, e, ranked[0][0]))
        else:
            found.append((s, e, None))
    return found


def repair_line(line, result, decided=()):
    """correction_entry の結果 result に、この段の直し・紫を足す。"""
    if not _on() or not isinstance(result, dict):
        return result
    import difflib
    done = result.get('corrected') or line
    try:
        marks = propose(done)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    out = dict(result)
    new = done
    details, odd_add, fixed = [], [], []
    # 後ろから置く（前の位置がずれない）
    for s, e, face in sorted(marks, key=lambda m: -m[0]):
        if any(x < e and s < y for x, y in list(decided or ())):
            continue
        if face:
            new = new[:s] + face + new[e:]
            details.append([done[s:e], face, '巻き込みの1打'])
            fixed.append((s, e))
        else:
            if any(x < e and s < y for x, y in changed):
                continue
            odd_add.append((s, e))
    if new == done and not odd_add:
        return result
    if odd_add:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, f'「{done[a:b]}」は、隣のキーを一緒に押した1字が入っているかもしれません') for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        # 直した所に掛かる紫は外す（位置は直す前の done の位置。直した所より後ろの紫は長さの差だけずらす）
        def keep(x):
            return not any(x[0] < fe and fs < x[1] for fs, fe in fixed)
        delta_at = sorted(fixed)

        def shift(p):
            d = 0
            for (fs, fe), (_s, _e, face) in zip(delta_at, sorted([m for m in marks if m[2]], key=lambda m: m[0])):
                if p >= fe:
                    d += len(face) - (fe - fs)
            return p + d
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [(shift(x[0]), shift(x[1])) + tuple(x[2:]) for x in out[key] if keep(x)]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [(shift(r[0]), shift(r[1])) + tuple(r[2:]) for r in out['odd_reasons'] if keep(r)]
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
