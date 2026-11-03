# -*- coding: utf-8 -*-
"""IME で読みを変換し直して、選び違いと1打の打ち違いの漢字の語を疑う段（2026-10-30・うにさん「定番の誤字をカバー」）。

行の漢字やカタカナの語は、打った読みを IME が変換したもの。世の中でめったに使わない語（wordfreq の段で珍しい語）が
行に出ているとき、次の2つを PC の IME（読み取りだけの IFELanguage）で確かめる。
1. 選び違い: 行の読みをそのまま IME で変換し直すと、その語の所が身近な語になる。
2. 1打の打ち違い: その語の読みの1打を戻した読み（ローマ字・かな入力ごと）で行を変換し直すと、身近な語になる。
どちらも行の費用（morphology.path_cost）が下がるときだけ候補にする。
選び違いで、IME 自身の最初の変換と同じ・語の所だけが替わる・珍しさの差が大きい ときは直す。ほかは紫。
雲の読みの格子で組んだ並びは無意味な語の並びを好むので、変換は IME に任せる（格子は1打の候補を絞るのにだけ使う）。
特定の語や文字列には合わせない（局所的な補正はしない）。IME が使えない環境では何もしない。
"""
import difflib
import gzip
import json
import os
from functools import lru_cache

DOUBT = 560        # wordfreq の段（大きいほど珍しい）。これ以上の語を疑う
DOUBT_MARK = 600   # 選び違いを紫にするのは、これ以上珍しい語
DOUBT_KEY = 700    # 1打の打ち違いを試すのは、これ以上珍しい語（表に無い語は 800）
COMMON = 470       # 替わった先の語はこれ以下（身近な語）
FIX_COMMON = 430   # 直すときの替わった先の語
JUMP = 100         # 元の語より、替わった先がこれだけ身近
FIX_JUMP = 200     # 直すときの差
MARK_GAIN = 1000   # 選び違い: 行の費用がこれだけ下がれば紫
KEY_GAIN = 3000    # 1打の打ち違い: 行の費用がこれだけ下がれば紫（切り方の揺れで下がる分より大きく）
KEY_TOP = 8        # 1打の候補は、格子で身近な語に組める読みのうち費用の安い順にこれだけ IME に渡す
MAX_WORDS = 2      # 窓の IME の語の数


def _kanji(c):
    return '一' <= c <= '鿿'


def _katakana(c):
    return 'ァ' <= c <= 'ヶ' or c == 'ー'


def _strong(s):
    return any(_kanji(c) or _katakana(c) for c in s)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


@lru_cache(maxsize=1)
def _freq():
    try:
        with gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ja_wordfreq.json.gz'),
                       'rt', encoding='utf-8') as f:
            return json.load(f)['words']
    except Exception:
        return {}


def _rank(face):
    return _freq().get(face, 800)


def _token_rarity(t, tokens=None):
    """解析の1語の珍しさ。かなだけの語・機能語は 0。活用する語は基本形で、表に無い名詞は身近な2つの語の組なら組の珍しさ。
    tokens（行の解析の並び）を渡すと、動詞の連用形の直後の動詞（書き｜換わる・飛び｜跳ねる の後ろ）は複合動詞の後ろの語
    なので、複合動詞が表に在ればその珍しさ、無ければ前の動詞の珍しさで見る（2026-11-03 うに 未解決タブ: 複合動詞の
    後ろの語だけを珍しい語と見て、正しい行を別の語に直した）。"""
    if not _strong(t.surface) or t.pos in ('助詞', '助動詞', '記号'):
        return 0
    face = t.surface
    if t.pos in ('動詞', '形容詞'):
        face = getattr(t, 'base_form', '') or face
    r = _rank(face)
    if tokens and t.pos == '動詞' and r >= DOUBT and os.environ.get('CN_RECONVERT_COMPOUND') != '0':
        prev = [p for p in tokens if p.end == t.start and p.pos == '動詞' and _strong(p.surface)]
        if prev and getattr(prev[0], 'base_form', '') and prev[0].surface != prev[0].base_form:
            whole = prev[0].surface + face
            return min(r, _freq().get(whole, _rank(prev[0].base_form)))
    if t.pos == '動詞' and r >= DOUBT and os.environ.get('CN_RECONVERT_COMPOUND_ONE') != '0':
        # 1語に解析された複合動詞（見入る・書き込む）は、前の動詞の連用形と後ろの動詞のどちらも身近なら、その珍しさで見る
        r2 = _compound_verb_rarity(face)
        if r2 is not None:
            r = min(r, r2)
    if r >= 800 and t.pos == '名詞':
        for k in range(1, len(face) - 1):
            a, b = face[:k], face[k:]
            if len(a) < 2 and not any('ぁ' <= c <= 'ゖ' for c in b):
                continue
            ra, rb = _rank(a), _rank(b)
            if ra <= 520 and rb <= 520:
                return max(ra, rb)
    return r


@lru_cache(maxsize=4096)
def _compound_verb_rarity(face):
    try:
        from morphology import tokenize
    except Exception:
        return None
    best = None
    for k in range(1, len(face) - 1):
        head, tail = face[:k], face[k:]
        if not _strong(head) or not _strong(tail[:1]):
            continue
        tt = list(tokenize(tail))
        if len(tt) != 1 or tt[0].pos != '動詞' or tt[0].surface != tail:
            continue
        ht = list(tokenize(head + 'ます'))
        if not ht or ht[0].pos != '動詞' or ht[0].surface != head or not getattr(ht[0], 'base_form', ''):
            continue
        v = max(_rank(ht[0].base_form), _rank(getattr(tt[0], 'base_form', '') or tail))
        best = v if best is None else min(best, v)
    return best


def _span_rarity(text, a, b, tokens):
    return max([_token_rarity(t, tokens) for t in tokens if t.start < b and a < t.end] + [0])


@lru_cache(maxsize=4096)
def _lattice_cost(reading):
    """1打の候補の読みが、格子で身近な語だけに組めるときの費用（組めなければ None）。"""
    try:
        import reading_lattice
        res = reading_lattice.best(reading)
    except Exception:
        return None
    if not res.surface or any(w[2] == '未知' for w in res.words):
        return None
    if max([_rank(w[0]) for w in res.words if _strong(w[0])] + [0]) > COMMON:
        return None
    return res.cost


def _key_readings(reading, input_method):
    out = []
    try:
        if input_method == 'romaji':
            import romaji_repair
            import romaji_swap_repair
            for spelled in romaji_swap_repair._spellings(reading, limit=2):
                found = romaji_repair.one_key_readings(spelled)
                out.extend(row[0] for row in getattr(found, 'candidates', ()))
        else:
            from contextual_repair import key_repairs
            out.extend(getattr(r, 'reading', r) for r in key_repairs(reading))
    except Exception:
        return []
    ranked = []
    for v in dict.fromkeys(out):
        if not v or v == reading:
            continue
        c = _lattice_cost(v)
        if c is not None:
            ranked.append((c, v))
    return [v for c, v in sorted(ranked)[:KEY_TOP]]


def _judge(text, here, other, s, e, tokens, src_rare, path_cost, tokenize):
    """変換し直した行が、窓の所だけ身近な語に替わり行の費用が下がるなら (下がった分, 替わった先の珍しさ, 変わった所)。"""
    if not other or other == text:
        return None
    ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops or ops[0][1] < s - 1 or ops[-1][2] > e + 1:
        return None
    j1, j2 = ops[0][3], ops[-1][4]
    new = [t for t in tokenize(other) if t.start < j2 and j1 < t.end]
    if any(not t.has_reading for t in new):
        return None
    rr = max([_token_rarity(t, new) for t in new] + [0])
    if not (0 < rr <= COMMON and src_rare - rr >= JUMP):
        return None
    c = path_cost(other)
    if c is None:
        return None
    return here - c, rr, (ops[0][1], ops[-1][2])


_EXTRA_FUNC = ('助詞', '助動詞')


def _extra_key(text, phon, words, here, path_cost, tokenize):
    """ローマ字で1打多く打って（同じキーの2度押し・隣のキーの巻き込み）、かなの続き（ください・おります）が
    珍しい漢字の語に変換された形。IME の読みと前後のかなをローマ字に戻して1打を抜き、かなのまま行に戻すと
    その所が付属の語（非自立の動詞・助動詞・助詞）だけになり、行の費用が大きく下がるものを探す。
    [(開始, 終了, 置く行 or None)]。候補が1つなら置く行、2つ以上なら紫。"""
    try:
        import romaji_swap_repair
        from halfwidth import romaji_to_kana
    except Exception:
        return []
    out = []
    for s, e, rs, re_ in [w[:4] for w in words]:
        face = text[s:e]
        if not face or not all(_kanji(c) for c in face) or _rank(face) < DOUBT_KEY:
            continue
        a = s
        while a > 0 and s - a < 2 and 'ぁ' <= text[a - 1] <= 'ゖ':
            a -= 1
        b = e
        while b < len(text) and b - e < 2 and 'ぁ' <= text[b] <= 'ゖ':
            b += 1
        found = set()
        for x in range(a, s + 1):
            for y in range(e, b + 1):
                typed_kana = text[x:s] + _hira(phon[rs:re_]) + text[e:y]
                for typed in romaji_swap_repair._spellings(typed_kana, limit=2):
                    for i in range(1, len(typed)):
                        k = romaji_to_kana(typed[:i] + typed[i + 1:])[0]
                        if not k or not all('ぁ' <= c <= 'ゖ' for c in k):
                            continue
                        other = text[:x] + k + text[y:]
                        new = [t for t in tokenize(other) if t.start < x + len(k) and x < t.end]
                        if (not new or new[0].start != x or new[-1].end != x + len(k)
                                or any(not t.has_reading for t in new)
                                or not all(t.pos in _EXTRA_FUNC or (t.pos == '動詞' and t.pos_sub.startswith('非自立'))
                                           for t in new)
                                or not any(t.pos != '助詞' for t in new)):
                            continue
                        c = path_cost(other)
                        if c is not None and here - c >= KEY_GAIN:
                            found.add(other)
        if found:
            out.append((s, e, found.pop() if len(found) == 1 else None))
    return out


_SMALL = 'ゃゅょぁぃぅぇぉ'


def _morae(reading):
    """読み → [(子音, 母音, 長音か)]。拗音は前の字と組、長音（えい・おう・ー・同じ母音）は前の拍に付ける。"""
    try:
        import romaji_swap_repair
    except Exception:
        return None
    units = []
    for c in reading:
        if c in _SMALL and units:
            units[-1] += c
        else:
            units.append(c)
    out = []
    for u in units:
        sp = romaji_swap_repair._spellings(u, limit=1)
        if not sp:
            return None
        sp = sp[0]
        vow = sp[-1] if sp[-1] in 'aiueo' else ''
        if out and not vow and u in 'ー':
            out[-1] = (out[-1][0], out[-1][1], True)
            continue
        if (out and u in 'いう' and not out[-1][2]
                and (out[-1][1][-1:], u) in (('e', 'い'), ('o', 'う'), ('u', 'う'), ('i', 'い'), ('a', 'あ'))):
            out[-1] = (out[-1][0], out[-1][1], True)
            continue
        cons = sp[:1] if sp[:1] not in 'aiueo' else ''
        out.append((cons, sp[len(cons):], False))
    return out


def _vowel_slip(a, b):
    """拍の数と長音が同じで、1拍だけ子音が同じまま母音（拗音を含む）が違う（れい／りょう）。"""
    ma, mb = _morae(a), _morae(b)
    if not ma or not mb or len(ma) != len(mb) or len(ma) < 2:
        return False
    diff = [(x, y) for x, y in zip(ma, mb) if x != y]
    return (len(diff) == 1 and diff[0][0][0] == diff[0][1][0] and diff[0][0][0] != ''
            and diff[0][0][2] == diff[0][1][2])


_SURU_HEAD = ('し', 'する', 'すれ', 'させ', 'され', 'いたし', 'いたす', '致し', '致す')


def _vowel_slip_noun(text, phon, words):
    """めったに使わない漢字の語＋する（しました・いたします）で、その語の読みが、名詞＋する の組の表の語の読みと
    1拍の母音だけ違う（じゅれい／じゅりょう）。表の語が1つなら直す、2つ以上なら紫。"""
    try:
        import collocation_repair
        _t, by_pv, _np, _w = collocation_repair.table()
    except Exception:
        return []
    nouns = set(by_pv.get(('続', 'する'), ())) | set(by_pv.get(('続', 'いたす'), ()))
    out = []
    for i in range(len(words)):
        for k in (1, 2):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e, rs, re_ = w[0][0], w[-1][1], w[0][2], w[-1][3]
            # IME が送りがなまで1語にした形（受領し）: 読みの終わりと同じかなを外す
            while e > s and not _kanji(text[e - 1]) and re_ > rs and _hira(phon[re_ - 1]) == text[e - 1]:
                e, re_ = e - 1, re_ - 1
            face = text[s:e]
            if (not face or not all(_kanji(c) for c in face) or _rank(face) < DOUBT_KEY
                    or not text.startswith(_SURU_HEAD, e) or (s > 0 and _kanji(text[s - 1]))):
                continue
            if any(x[0] == s and x[1] == e for x in out):
                continue
            # 読みは IME の逆変換（受 を うけ と読むことがある）と、字ごとの読みの組（じゅ＋りょう）の両方で見る
            typed = {_hira(phon[rs:re_])}
            try:
                import kanji_guess
                typed.update(kanji_guess.reading_combos(face)[:12])
            except Exception:
                pass
            cands = sorted(c for c in nouns if c != face and any(
                r == (collocation_repair._word_reading(c) or '') or _vowel_slip(r, collocation_repair._word_reading(c) or '')
                for r in typed))
            if cands:
                out.append((s, e, text[:s] + cands[0] + text[e:] if len(cands) == 1 else None))
    return out


RESEG_TIE = 300     # 区切り直し: 2番目の並びとの費用の差がこれより小さければ紫
_HIRAGANA = ''.join(chr(x) for x in range(0x3041, 0x3097))
RESEG_SLACK = 1500  # 区切り直し: 左右とも身近でない語のときに許す費用の上がり


def _reseg_faces(reading, cut=0):
    """読みを格子で区切り直した表記の並び。境目（cut）より後ろのかなのままの語は、同じ読みの身近な漢字の名詞が
    在ればそちらだけにする（元はIMEが漢字にした所なので）。"""
    try:
        import reading_lattice
        reading_lattice.load()
        # 世の中で珍しい語は高くして、身近な語の並びを選ぶ（かいとうあん → 甲斐＋東庵 でなく 回答＋案）
        res = reading_lattice.best(reading, word_cost=lambda surf, key, cost:
                                   cost + (KEY_GAIN if _strong(surf) and _rank(surf) > COMMON else 0))
    except Exception:
        return []
    if not res.surface or any(w[2] == '未知' for w in res.words):
        return []
    outs = ['']
    at = 0
    for w in res.words:
        alts = [w[0]]
        start, at = at, at + len(w[1])
        if not _strong(w[0]) and (w[2] == '名詞' or start >= cut):
            # IME は名詞を漢字にするので、身近な漢字の名詞が在ればそちらだけ
            alts = sorted({surf for surf, _l, _r, _c, pos in reading_lattice._table.get(w[1], ())
                           if pos == '名詞' and _strong(surf) and _rank(surf) <= COMMON}) or alts
        outs = [o + a for o in outs for a in alts][:64]
    return outs


def _reseg_scored(text, phon, s0, e0, r0, s1, e1, r1, q1, tokens, here, path_cost, tokenize):
    """左の語 [s0, e0) と珍しい語 [s1, e1) の読みを区切り直した行と費用の並び。"""
    if _span_rarity(text, s1, e1, tokens) < DOUBT or _span_rarity(text, s0, e0, tokens) >= DOUBT:
        return []
    both_odd = _span_rarity(text, s0, e0, tokens) > COMMON
    cut = len(_hira(phon[r0:r1]))
    reading = _hira(phon[r0:q1])
    scored = []
    for face in _reseg_faces(reading, cut):
        # 左の語が身近な語なら、そのままの表記で残る並びだけ（お客｜さまよう → お客様用）。左の語も
        # 身近でなければ（怪盗｜あんです）左の語ごと区切り直してよい
        if not all(_kanji(ch) or _katakana(ch) or 'ぁ' <= ch <= 'ゖ' for ch in face):
            continue
        if face == text[s0:e1] or (not face.startswith(text[s0:e0]) and not both_odd):
            continue
        other = text[:s0] + face + text[e1:]
        new = [t for t in tokenize(other) if t.start < s0 + len(face) and s0 < t.end]
        if not new or any(not t.has_reading for t in new):
            continue
        if any(_strong(t.surface) and _token_rarity(t, new) > COMMON for t in new):
            continue
        # 同じ字の語が続く並び（様＋様）は変換の重なりで、区切り直しの答えにしない
        if any(a.surface.endswith(b.surface) and _strong(b.surface) for a, b in zip(new, new[1:])):
            continue
        # 元の境目（左の語の読みの終わり）をまたぐ語が在ること（区切りが替わった）
        pos, crosses = 0, False
        for t in new:
            r = len(_hira(t.reading))
            if pos < cut < pos + r:
                crosses = True
            pos += r
        if not crosses and not both_odd:
            continue
        # 左右とも身近でない語の区切り直しは、語の部分が漢字・カタカナだけのもの（後ろの です などは別）
        relaxed_ok = not any('ぁ' <= ch <= 'ゖ' for ch in face.rstrip(_HIRAGANA))
        c = path_cost(other)
        # 行の費用が大きく下がる。または、左右とも身近でない語（怪盗＋アンデス）が身近な語だけの並びになり、
        # 費用がほとんど上がらない（名詞2つの並びは安いので、下がり方では見えない）
        if c is not None and (here - c >= KEY_GAIN or (both_odd and relaxed_ok and c - here <= RESEG_SLACK)):
            scored.append((c, other))
    return sorted(scored)


def _resegment(text, phon, words, here, path_cost, tokenize):
    """IME が読みの区切りを違えた形（おきゃくさま｜よう を お客｜さまよう と区切った）。珍しい語とその左の語の読みを
    格子で区切り直し、二つの語の境目をまたぐ身近な語の並びになって行の費用が大きく下がるなら、いちばん安い並びに直す。
    2番目と費用が近ければ紫。"""
    out = []
    tokens = None
    for i in range(1, len(words)):
        (s0, e0, r0, _q0), (s1, e1, r1, q1) = words[i - 1][:4], words[i][:4]
        if e0 != s1 or not _strong(text[s0:e0]) or not _strong(text[s1:e1]):
            continue
        if tokens is None:
            tokens = list(tokenize(text))
        ends = [(e1, q1)]
        # IME が送りがなを別の語にした形（彷徨｜う）: 続くかなだけの短い語を含めた形を先に見る（含めないと 様＋夜 のような切れ端が残る）
        if (i + 1 < len(words) and words[i + 1][0] == e1 and words[i + 1][1] - words[i + 1][0] <= 2
                and all('ぁ' <= ch <= 'ゖ' for ch in text[words[i + 1][0]:words[i + 1][1]])):
            ends.insert(0, (words[i + 1][1], words[i + 1][3]))
        for e, q in ends:
            scored = _reseg_scored(text, phon, s0, e0, r0, s1, e, r1, q, tokens, here, path_cost, tokenize)
            if scored:
                sure = len(scored) == 1 or scored[1][0] - scored[0][0] >= RESEG_TIE
                out.append((s1, e, scored[0][1] if sure else None))
                break
    return out


def propose(text, input_method='kana', ime=None):
    """[(開始, 終了, 置く行 or None)]。置く行があれば直す、None は紫。"""
    if not _freq() or ime is None or not text or not _strong(text):
        return []
    from morphology import path_cost, tokenize
    tokens = list(tokenize(text))
    if max([_token_rarity(t, tokens) for t in tokens] + [0]) < DOUBT:
        return []
    rw = ime.reverse_words(text)
    if not rw:
        return []
    phon, words = rw
    here = path_cost(text)
    if here is None:
        return []
    misread = _misread_spans(text, phon, words, tokens)
    first = None
    picked = _extra_key(text, phon, words, here, path_cost, tokenize) if input_method == 'romaji' else []
    picked += [m for m in _vowel_slip_noun(text, phon, words) if not any(a < m[1] and m[0] < b for a, b, _f in picked)]
    picked += [m for m in _resegment(text, phon, words, here, path_cost, tokenize) if not any(a < m[1] and m[0] < b for a, b, _f in picked)]
    for i in range(len(words)):
        for k in range(1, MAX_WORDS + 1):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e, rs, re_ = w[0][0], w[-1][1], w[0][2], w[-1][3]
            if not _strong(text[s:e]):
                continue
            src_rare = _span_rarity(text, s, e, tokens)
            if src_rare < DOUBT or any(a < e and s < b for a, b, _f in picked):
                continue
            if first is None:
                first = ime.convert(phon) or ''
            found = None
            same = _judge(text, here, first, s, e, tokens, src_rare, path_cost, tokenize)
            if same is not None:
                gain, rr, (a, b) = same
                # 直すのは、表に無いほど珍しい語が IME 自身の変換で身近な語に替わるときだけ（迷うなら紫）
                if (s <= a and b <= e and src_rare >= DOUBT_KEY and src_rare - rr >= FIX_JUMP and rr <= FIX_COMMON
                        and gain >= MARK_GAIN):
                    found = (s, e, first)
                elif src_rare >= DOUBT_MARK and gain >= MARK_GAIN:
                    found = (s, e, None)
            if found is None and src_rare >= DOUBT_KEY:
                reading = _hira(phon[rs:re_])
                for v in _key_readings(reading, input_method):
                    other = ime.convert(phon[:rs] + v + phon[re_:])
                    got = _judge(text, here, other, s, e, tokens, src_rare, path_cost, tokenize)
                    if got is not None and got[0] >= KEY_GAIN:
                        found = (s, e, None)
                        break
            if found is not None:
                # 紫は窓の中の珍しい語だけに付ける（前後の助詞などは含めない）
                rare = [t for t in tokens if t.start < e and s < t.end and _token_rarity(t, tokens) >= DOUBT]
                if rare and found[2] is None:
                    found = (max(s, rare[0].start), min(e, rare[-1].end), None)
                picked.append(found)
    # IME が本文の語を辞書と違う読みで読んだ所（浅煎り を せんいり）は、その読みからの直しも紫も出さない（2026-10-31）
    # 置く行が印の外まで書き換えるとき（印は 煎り、置く行は 浅 も変える）は、書き換わる所全体で見る
    return [m for m in picked if not _touches(m, misread, text)]


def _changed_span(text, line):
    """text と置く行 line の違う所 (s, e)（text の側の位置）。同じなら None。"""
    if line == text:
        return None
    a = 0
    while a < len(text) and a < len(line) and text[a] == line[a]:
        a += 1
    b = 0
    while b < len(text) - a and b < len(line) - a and text[-1 - b] == line[-1 - b]:
        b += 1
    return a, len(text) - b


def _touches(m, spans, text):
    s, e = m[0], m[1]
    if m[2] is not None:
        ch = _changed_span(text, m[2])
        if ch is not None:
            s, e = min(s, ch[0]), max(e, ch[1])
    return any(a < e and s < b for a, b in spans)


def _misread_spans(text, phon, words, tokens):
    """IME の逆変換の読みが、同じ所の辞書の読み（解析の語の読みをつないだもの）と食い違う IME の語の範囲 → [(s, e)]。
    辞書の語の切れ目が IME の語の端と揃い、どの語も読みを持つ所だけ比べる（揃わない所は比べない）。
    IME が辞書の1語を2つ以上に切ったとき（浅｜煎り）は、続く IME の語をつないで揃う所で比べる（2026-10-31）。"""
    out = []
    for i in range(len(words)):
        for k in range(1, MAX_WORDS + 1):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e, rs, re_ = w[0][0], w[-1][1], w[0][2], w[-1][3]
            inside = [t for t in tokens if t.start < e and s < t.end]
            if not inside or inside[0].start != s:
                break
            if inside[-1].end != e:
                continue                     # 辞書の語の途中で切れている: 次の IME の語までつなぐ
            if not _strong(text[s:e]):
                break
            if not all(getattr(t, 'has_reading', True) and t.reading for t in inside):
                break
            # 辞書の読みが確かな所だけ: 送りがなの在る語（浅煎り）か、辞書の1語の漢字の並び。漢字1字ずつに切れた並び
            # （打ち違いで出来た珍しい字の組）は字ごとの読みが当てにならないので比べない
            if not (any('ぁ' <= c <= 'ゖ' for c in text[s:e]) or len(inside) == 1):
                break
            mine = _hira(''.join(t.reading for t in inside))
            if mine != _hira(phon[rs:re_]):
                out.append((s, e))
            break
    return out


def repair_line(line, result, input_method='kana', decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:
                return result
            marks = propose(done, input_method, ime)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    odd_add, details = [], []
    # 直しは行ごとの置き換えなので、最初の1つだけ（ほかは紫）
    fixed = None
    for s, e, other in marks:
        if any(x < e and s < y for x, y in changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        if other and not fixed:
            ops = [o for o in difflib.SequenceMatcher(None, done, other, autojunk=False).get_opcodes() if o[0] != 'equal']
            new = done[:ops[0][1]] + other[ops[0][3]:ops[-1][4]] + done[ops[-1][2]:]
            details.append([done[ops[0][1]:ops[-1][2]], other[ops[0][3]:ops[-1][4]], 'IMEの選び違い'])
            fixed = org
        elif not any(x < org[1] and org[0] < y for x, y in odd_now):
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if fixed:
        # 直した所に前の段が付けた紫は外す
        out['odd_spans'] = [x for x in (result.get('odd_spans') or ()) if not (x[0] < fixed[1] and fixed[0] < x[1])]
        out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ())
                              if not (r[0] < fixed[1] and fixed[0] < r[1])]
        if result.get('unsure_spans'):
            out['unsure_spans'] = [x for x in result['unsure_spans'] if not (x[0] < fixed[1] and fixed[0] < x[1])]
    if odd_add:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」はあまり使わない語です。同じ読みか1打違いの読みで変換し直すと、より自然な文になります')
            for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
