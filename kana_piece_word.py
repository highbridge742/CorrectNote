# -*- coding: utf-8 -*-
"""かなの切れ端を語に戻す段（kana_piece_word・2026-11-08 手分けA・うにさん 補正担当へ「5時間続けて」）。

1. 名詞＋紫のかなの切れ端（しょくじけん → 食事｜けん の けん に紫）: 切れ端の読みの漢字1〜2字を前の名詞に付けると
   辞書（JMdict の名詞の表 jm_noun_kind・語の表 seed_japanese）に1語として在る組が1つだけなら、その組にする
   （食事＋券 は在る・食事＋圏／権／県 は無い）。2つ以上なら紫のまま。前の段が紫を付けた所だけを見る。
2. かなだけの短い並び（行や句読点・括弧で区切られた2〜5字）で、文の形に説明が付かず語でもないもの（たふせ）:
   1打の戻し（かな入力ならキーの隣・゛゜の取り違え、ローマ字なら1キー）で、身近な名詞1語（辞書の表に在る語）に
   なる読みが1つだけなら直す（たふ＋せ → たぶ: せ と ゛ は隣のキー → タブ）。2つ以上なら紫。

特定の語や文字列には合わせない。ime_reconvert.repair_line の最後（rollin_word の後）から呼ぶ。
切り替え: CN_KANA_PIECE_WORD=0 で何もしない。1だけ止める CN_KANA_PIECE_SUFFIX=0、2だけ止める CN_KANA_PIECE_SHORT=0。
"""
import os
from functools import lru_cache

SHORT_COMMON = 520   # 2: 直す先の語の身近さ（ime_reconvert._rank）
SHORT_MIN, SHORT_MAX = 3, 5
SUFFIX_MAX = 3       # 1: 切れ端の長さ（字）
PIECE_MIN = 1 if os.environ.get('CN_KANA_PIECE_ONE') == '1' else 2
_STOP = frozenset('、。，．,.!?！？\t 　「」『』（）()【】［］[]・…\n')
_SMALL = 'ゃゅょぁぃぅぇぉっゎ'


def _on(name):
    return os.environ.get('CN_KANA_PIECE_WORD') != '0' and os.environ.get(name) != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(c):
    return 'ぁ' <= c <= 'ゖ' or c == 'ー'


def _rank(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face)
    except Exception:
        return 800


@lru_cache(maxsize=1)
def _jm():
    try:
        import context_skeleton
        return context_skeleton._jm_nouns()
    except Exception:
        return {}


@lru_cache(maxsize=8192)
def _unit(face):
    try:
        import seed_japanese
        return seed_japanese.is_unit(face) is True
    except Exception:
        return False


def _is_word(face):
    return face in _jm() or _unit(face)


@lru_cache(maxsize=8192)
def _pos(face):
    try:
        from morphology import dictionary_base_pos
        return frozenset(dictionary_base_pos(face) or ())
    except Exception:
        return frozenset()


@lru_cache(maxsize=8192)
def _faces(reading, limit=20):
    try:
        import ime_reconvert
        return tuple(ime_reconvert._dict_faces(reading, limit))
    except Exception:
        return ()


def _explained(run, before='', after=''):
    try:
        import pos_grammar
        return bool(pos_grammar.explain_kana_run(run, after_kanji=bool(before) and _kanji(before[-1]),
                                                 kanji_stem='', before_kanji=bool(after) and _kanji(after[0]),
                                                 bare_head=True))
    except Exception:
        return True


def _overlaps(a, b, spans):
    return any(x < b and a < y for x, y in spans)


# ------------------------------------------------------------
# 1. 名詞＋紫のかなの切れ端
# ------------------------------------------------------------
def _rest_ok(rest, after):
    """切れ端の後ろのかな（を・が・です…）が、名詞の後ろに続く形か。"""
    try:
        from morphology import tokenize
        head = next(iter(tokenize(rest)), None)
    except Exception:
        head = None
    if head is not None and head.start == 0 and head.pos in ('助詞', '助動詞'):
        return True
    return _explained(rest, before='名', after=after)


def _suffix_marks(text, odd, placed=()):
    """odd: 前の段の紫（text の位置）。placed: 前の段がかなから漢字に置いた所（text の位置）。"""
    out = []
    if not odd and not placed:
        return out
    from morphology import tokenize
    toks = list(tokenize(text))
    for t in toks:
        if t.pos != '名詞' or len(t.surface) < 2 or not all(_kanji(c) for c in t.surface):
            continue
        a = t.end
        j = a
        while j < len(text) and _hira(text[j]):
            j += 1
        if j == a:
            continue
        found = {}
        # 切れ端は2字から（1字のかな: 時間｜や｜が の や は、巻き込み・余分な1打のことが多く、時間屋 にしない・2026-11-08）
        is_placed = os.environ.get('CN_KANA_PIECE_PLACED') != '0' and any(
            x < t.end and t.start < y and y == a for x, y in placed)
        # かなの行で前の段が置いた名詞の後ろの1字（こうりつ｜か）は、名詞＋接尾の1字の語（効率化）を見る
        # （紫の1字 時間｜や は見ない: 巻き込み・余分な1打のことが多い）。CN_KANA_PIECE_PLACED_ONE=0 で前のまま
        low = 1 if (is_placed and os.environ.get('CN_KANA_PIECE_PLACED_ONE') != '0') else PIECE_MIN
        for k in range(low, min(SUFFIX_MAX, j - a) + 1):
            piece = text[a:a + k]
            if k == 1 and low == 1 and PIECE_MIN > 1:
                rest1 = text[a + 1:j]
                after = text[j:j + 1]
                if (after and after in '?？') or (rest1 and not _rest_ok(rest1, after)):
                    continue
            # 切れ端の頭・後ろが音の途中（小書き・ん・ー の前で切る）なら見ない（経済｜け｜ん → 経済家 にしない）
            if piece[0] in _SMALL or (a + k < len(text) and text[a + k] in _SMALL + 'んー'):
                continue
            # 前の段が紫にした切れ端か、かなの行で前の段が漢字に置いた名詞のすぐ後ろに残ったかな（しょくじ｜けん）
            if not _overlaps(a, a + k, odd) and not (
                    os.environ.get('CN_KANA_PIECE_PLACED') != '0'
                    and any(x < t.end and t.start < y and y == a for x, y in placed)):
                continue
            rest = text[a + k:j]
            if rest and not _rest_ok(rest, text[j:j + 1]):
                continue
            for f in _faces(piece):
                if not (1 <= len(f) <= 2 and all(_kanji(c) for c in f)):
                    continue
                whole = t.surface + f
                if _is_word(whole) and not _is_word(t.surface + piece):
                    found.setdefault((a, a + k), set()).add(f)
        cands = [(sp, f) for sp, fs in found.items() for f in fs]
        if len(cands) == 1:
            (s, e), f = cands[0]
            out.append((s, e, f))
    return out


# ------------------------------------------------------------
# 3. かなの行で、置いた漢字の名詞のすぐ前に残った動詞の連用形（ひきつぎ｜資料）
# ------------------------------------------------------------
RENYOU_COMMON = 600   # 連用形の名詞の表記の身近さ（引き継ぎ 543）


def _renyou_marks(text, placed):
    """動詞の連用形＋漢語の名詞 の複合語（引き継ぎ資料・取り扱い説明）で、前の段が名詞だけ漢字にし、連用形をかなに
    残した所。連用形を漢字＋送り仮名の表記（表に在る一番身近なもの）にする。かなの名詞（おもちゃ・ものさし）は見ない
    （解析が動詞と見た語だけ）。CN_KANA_PIECE_RENYOU=0 で無し（2026-11-08 手分けA）。"""
    out = []
    if not placed or os.environ.get('CN_KANA_PIECE_RENYOU') == '0':
        return out
    from morphology import tokenize
    toks = list(tokenize(text))
    for i, t in enumerate(toks[:-1]):
        nxt = toks[i + 1]
        if t.pos != '動詞' or not all('ぁ' <= c <= 'ゖ' for c in t.surface) or len(t.surface) < 3:
            continue
        if nxt.start != t.end or nxt.pos != '名詞' or not all(_kanji(c) for c in nxt.surface) or len(nxt.surface) < 2:
            continue
        if not any(x <= nxt.start and nxt.end <= y for x, y in placed):
            continue
        # 連用形（後ろが い段）で、前の語に付いていない（行の頭か、助詞・記号の後ろ）
        if i > 0 and toks[i - 1].end == t.start and toks[i - 1].pos not in ('助詞', '記号'):
            continue
        faces = [f for f in _faces(t.surface, 12)
                 if any(_kanji(c) for c in f) and 'ぁ' <= f[-1] <= 'ゖ' and f[-1] == t.surface[-1]
                 and _rank(f) <= RENYOU_COMMON and any(p.startswith('名詞') for p in _pos(f))]
        if faces:
            out.append((t.start, t.end, min(faces, key=_rank)))
    return out


# ------------------------------------------------------------
# 4. かなの並びの中の 漢字1字の漢語＋する の動詞（さっして → 察して）
# ------------------------------------------------------------
SAHEN_COMMON = 520    # 置く表記の身近さ（察し 502・適し 505・接し 505）
SAHEN_OTHER = 600     # 同じ読みのほかの漢字の表記がこれ以下なら決まらない（かんし → 関し 596・冠し 600）
_SAHEN_TAIL = tuple('しじせぜすずさざ')


def _sahen_marks(text):
    """かなの並びを読みの格子（reading_lattice）で切り、動詞の所が 漢字1字＋サ変の活用の字（察し・適し・感じ）で、
    その漢字が音読み（漢語: kana_keep.is_kango）なら、その表記にする（うに 11-01: 漢語は漢字に、和語はかなのまま）。
    同じ読みの動詞の漢字の表記がほかにも身近なら（関し／冠し）決めない。文節の頭（行頭・助詞の後ろ）の動詞だけ。
    CN_KANA_PIECE_SAHEN=0 で無し（2026-11-08 手分けA）。"""
    out = []
    if os.environ.get('CN_KANA_PIECE_SAHEN') == '0':
        return out
    try:
        import reading_lattice
        import kana_keep
        import ime_reconvert
        table = ime_reconvert._dict_table()
    except Exception:
        return out
    i, n = 0, len(text)
    while i < n:
        if not _hira(text[i]) or text[i] == 'ー':
            i += 1
            continue
        j = i
        while j < n and _hira(text[j]):
            j += 1
        if j - i >= 3:
            try:
                res = reading_lattice.best(text[i:j])
            except Exception:
                res = None
            if res is not None and res.words and ''.join(w[1] for w in res.words) == text[i:j]:
                at = i
                for k, (face, rd, pos, _o) in enumerate(res.words):
                    a, b = at, at + len(rd)
                    at = b
                    if pos != '動詞' or len(face) < 2 or not _kanji(face[0]) or any(_kanji(c) for c in face[1:]):
                        continue
                    tail = face[1:]
                    if not tail or tail[0] not in _SAHEN_TAIL or not rd.endswith(tail) or len(rd) <= len(tail):
                        continue
                    if k > 0 and res.words[k - 1][2] != '助詞':
                        continue
                    # 音読みは2字の読み（さっ・あい・かん）だけ（1字の け は 消す の訓の語幹と同じ形で、音読みと見分けられない）
                    if len(rd) - len(tail) < 2 or not kana_keep.is_kango(face[0], rd[:-len(tail)]):
                        continue
                    faces = {x[0] for x in table.get(rd, ()) if x[4] == '動詞' and any(_kanji(c) for c in x[0])}
                    if face not in faces or _rank(face) > SAHEN_COMMON:
                        continue
                    if any(f != face and _rank(f) <= SAHEN_OTHER for f in faces):
                        continue
                    out.append((a, b, face))
        i = j
    return out


# ------------------------------------------------------------
# 2. かなだけの短い並び
# ------------------------------------------------------------
def _short_runs(text):
    out = []
    i = 0
    n = len(text)
    while i < n:
        if not _hira(text[i]):
            i += 1
            continue
        j = i
        while j < n and _hira(text[j]):
            j += 1
        left_ok = i == 0 or text[i - 1] in _STOP
        right_ok = j == n or text[j] in _STOP
        if left_ok and right_ok and SHORT_MIN <= j - i <= SHORT_MAX:
            out.append((i, j))
        i = j
    return out


def _one_key(run, input_method):
    try:
        if input_method == 'romaji':
            import romaji_repair
            import romaji_swap_repair
            out = []
            for spelled in romaji_swap_repair._spellings(run, limit=2):
                found = romaji_repair.one_key_readings(spelled)
                out.extend(row[0] for row in getattr(found, 'candidates', ()))
            return out
        from contextual_repair import key_repairs
        return [getattr(r, 'reading', r) for r in key_repairs(run)]
    except Exception:
        return []


_VOICED = {a: b for a, b in zip('かきくけこさしすせそたちつてとはひふへほ',
                                'がぎぐげござじずぜぞだぢづでどばびぶべぼ')}


def _substituted(run, v):
    """v は run の1字を別のキーの字に替えた形か（同じ長さで1字違い、または1字を ゛゜ に替えて前の字に付けた形:
    たふせ → たぶ）。字を抜く・足す・入れ替える形は語に化けやすいので見ない（かもね → かね）。"""
    if len(v) == len(run):
        return sum(x != y for x, y in zip(run, v)) == 1
    if len(v) == len(run) - 1:
        for i in range(1, len(run)):
            if run[:i - 1] == v[:i - 1] and run[i + 1:] == v[i:] \
                    and v[i - 1] in (_VOICED.get(run[i - 1]), _SEMI.get(run[i - 1])) and v[i - 1] is not None:
                return True
    return False


_SEMI = {a: b for a, b in zip('はひふへほ', 'ぱぴぷぺぽ')}


def _noun_face(reading):
    """読み1つが身近な名詞1語になる表記（一番身近なもの）か None。"""
    best = None
    for f in _faces(reading, 12):
        if not _is_word(f) or _rank(f) > SHORT_COMMON:
            continue
        if not any(p.startswith('名詞') for p in _pos(f)):
            continue
        if best is None or _rank(f) < _rank(best):
            best = f
    return best


def _short_marks(text, input_method):
    out = []
    for s, e in _short_runs(text):
        run = text[s:e]
        if _is_word(run) or _explained(run):
            continue
        if any(_is_word(f) and _rank(f) <= SHORT_COMMON for f in _faces(run, 12)):
            continue
        cands = {}
        for v in dict.fromkeys(_one_key(run, input_method)):
            if not v or v == run or len(v) < 2 or not _substituted(run, v):
                continue
            f = _noun_face(v)
            if f:
                cands[v] = f
        if len(cands) == 1:
            out.append((s, e, next(iter(cands.values()))))
        elif cands:
            out.append((s, e, None))
    return out


def propose(text, odd=(), input_method='kana', placed=()):
    """[(開始, 終了, 置く表記 or None)]（text の位置）。"""
    if not text or os.environ.get('CN_KANA_PIECE_WORD') == '0':
        return []
    marks = []
    if _on('CN_KANA_PIECE_SUFFIX'):
        marks.extend(_suffix_marks(text, [tuple(x[:2]) for x in odd], placed))
    if placed:
        marks.extend(m for m in _renyou_marks(text, placed) if not _overlaps(m[0], m[1], [x[:2] for x in marks]))
    marks.extend(m for m in _sahen_marks(text) if not _overlaps(m[0], m[1], [x[:2] for x in marks]))
    if _on('CN_KANA_PIECE_SHORT'):
        marks.extend(m for m in _short_marks(text, input_method) if not _overlaps(m[0], m[1], [x[:2] for x in marks]))
    return sorted(marks)


def repair_line(line, result, input_method='kana', decided=()):
    """correction_entry の結果 result に、この段の直し・紫を足す。"""
    if os.environ.get('CN_KANA_PIECE_WORD') == '0' or not isinstance(result, dict):
        return result
    import difflib
    done = result.get('corrected') or line
    odd = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    placed = []
    if line != done:
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
            if tag != 'equal' and j2 > j1 and all(_hira(c) for c in line[i1:i2]) and any(_kanji(c) for c in done[j1:j2]):
                placed.append((j1, j2))
    try:
        marks = propose(done, odd, input_method, placed)
    except Exception:
        return result
    if not marks:
        return result
    # done の位置 → line の位置（変わっていない所だけ）
    ops = difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes()

    def to_line(s, e):
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and i1 <= s and e <= i2:
                return (s - i1 + j1, e - i1 + j1)
        return None
    new = done
    details, odd_add, fixed = [], [], []
    for s, e, face in sorted(marks, key=lambda m: -m[0]):
        org = to_line(s, e)
        if org is not None and _overlaps(org[0], org[1], list(decided or ())):
            continue
        if face:
            new = new[:s] + face + new[e:]
            details.append([done[s:e], face, 'かなの切れ端'])
            fixed.append((s, e, face))
        elif not _overlaps(s, e, odd):
            odd_add.append((s, e))
    if new == done and not odd_add:
        return result
    out = dict(result)
    if odd_add:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, f'「{done[a:b]}」は語になりません。1打の打ち違いかもしれません') for a, b in odd_add]
    if new != done:
        def shift(p):
            d = 0
            for fs, fe, face in fixed:
                if p >= fe:
                    d += len(face) - (fe - fs)
            return p + d

        def keep(x):
            return not any(x[0] < fe and fs < x[1] for fs, fe, _f in fixed)
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [(shift(x[0]), shift(x[1])) + tuple(x[2:]) for x in out[key] if keep(x)]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [(shift(r[0]), shift(r[1])) + tuple(r[2:]) for r in out['odd_reasons'] if keep(r)]
        lops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details[::-1],
                    'spans': [[o[3], o[4]] for o in lops], 'original_spans': [[o[1], o[2]] for o in lops]})
    return out
