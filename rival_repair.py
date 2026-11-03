# -*- coding: utf-8 -*-
"""前の段が直した語を、打った読みのほかの1打の戻しと例文の組で比べ直す段（rival_repair・手分けA・2026-11-01）。

かな入力の1打の打ち違いは、戻し方が1つとは限らない。ば（は＋゛）は「゛を抜く」でも「は を隣の し に替える（じ）」でも
1打の戻しになる。前の段は1つを選ぶ（多くは抜く形）が、選んだ語が実在の語なら紫も付かず、そのまま漢字に変換される。
ここでは、前の段が替えた所の語について、元の行で打った読みの1打の戻しを全部並べ、それぞれの読みの名詞を例文の組の表
（pair_choice の Tatoeba の表: 名詞＋の＋名詞・名詞＋助詞＋述語・名詞＋直後の述語 など）で数える。
  - 一番の名詞の組が FIX_PAIR 以上・二番（今の答えの読みの名詞も含む）の RATIO 倍以上で、今の答えと読みが違えば、その名詞に替える。
  - 一番が今の答えの読み、または決め手が無ければ何もしない（前の段の答えのまま）。
前の段が何も替えていない語（打ったままの実在の語）は見ない。かな入力だけ。特定の語や文字列には合わせない。
"""
import difflib

FIX_PAIR = 5      # 一番の名詞の組がこれだけ例文に在ること
RATIO = 4         # 二番よりこれだけ多いこと
MAX_READ = 10     # 見る語の読みの長さ
COST_SLACK = 500  # 替えた行の並びの費用が今の行よりこれ以上重ければ替えない（漢字に変換した後の行は、同じ読みの長さの語どうしで費用が並ぶ）


# 語の頭の前に来てよい平仮名の語（よく使う助詞・助動詞の形。解析が1字のかなを助詞と見誤ることがあるので品詞では見ない）
_HEAD_AFTER = {'は', 'が', 'を', 'に', 'で', 'と', 'も', 'の', 'へ', 'や', 'から', 'まで', 'より', 'か', 'ね', 'よ',
               'って', 'だ', 'です', 'ます', 'た', 'て', 'ので', 'のに', 'けど', 'し', 'でも', 'など', 'ば'}


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _is_hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in s)


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _nouns(reading):
    """読みの名詞（漢字だけの表記・2字以上）。"""
    import reading_lattice
    reading_lattice.load()
    return {s for s, _l, _r, _c, pos in reading_lattice._table.get(reading, ())
            if pos == '名詞' and len(s) >= 2 and all(_kanji(c) for c in s)}


def _score(pairs, ctx, noun):
    import pair_choice as P
    return max((P._count(pairs, k, l, r, noun) for k, l, r in ctx), default=0)


def _to_line(allops, p, start):
    """done の位置 p → line の位置。替えた所の中なら、その所の端（start なら前の端）。"""
    for tag, i1, i2, j1, j2 in allops:
        if tag == 'equal' and j1 <= p <= j2:
            return i1 + p - j1
    for tag, i1, i2, j1, j2 in allops:
        if tag != 'equal' and j1 <= p <= j2:
            return i1 if start else i2
    return None


def propose(line, done):
    """[(done の開始, 終了, 置く名詞)]。"""
    import pair_choice as P
    import morphology
    from morphology import tokenize
    from contextual_repair import key_repairs
    tab = P._table()
    if not tab or line == done:
        return []
    pairs, _nouns_count = tab
    allops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    ops = [o for o in allops if o[0] != 'equal']
    if not ops:
        return []
    toks = list(tokenize(done))
    out = []
    for i, t in enumerate(toks):
        if t.pos != '名詞' or not t.has_reading:
            continue
        # 語の頭: 行頭・記号・助詞・助動詞・漢字の語のすぐ後ろ（けいそ を け＋いそ と区切った いそ のような語の途中を見ない）
        if i > 0 and _is_hira(toks[i - 1].surface) and (toks[i - 1].surface not in _HEAD_AFTER or i == 1):
            continue      # 行頭のかな1語（助詞に見えても）のすぐ後ろは語の途中の区切り違いとみる
        cur = _hira(t.reading)
        if not _is_hira(cur) or len(cur) > MAX_READ:
            continue
        # 前の段が替えた所を含む語だけ（語の中に替えた所が在り、語の外には掛からない）
        mine = [o for o in ops if t.start <= o[3] and o[4] <= t.end and (o[3] < o[4] or t.start < o[3] < t.end)]
        if not mine or any(o[3] < t.end and t.start < o[4] and not (t.start <= o[3] and o[4] <= t.end) for o in ops):
            continue
        # 元の行の、その語に当たる所（打ったまま）
        s0, e0 = _to_line(allops, t.start, True), _to_line(allops, t.end, False)
        if s0 is None or e0 is None or s0 >= e0:
            continue
        typed = line[s0:e0]
        if not _is_hira(typed) or typed == cur:
            continue      # 読みを替えずに漢字を置いただけの所（打ったままの語）は見ない
        ctx = P._contexts(toks, i)
        if not ctx:
            continue
        cands = {}
        for r in key_repairs(typed, line[:s0][-1:], line[e0:][:1]):
            r = getattr(r, 'reading', r)
            if not r or r == typed:
                continue
            for n in _nouns(r):
                c = _score(pairs, ctx, n)
                if c > cands.get(n, (0, ''))[0]:
                    cands[n] = (c, r)
        # 今の答えの読みの名詞と、打ったままの読みの名詞も競う側に入れる
        for rr in (cur, typed):
            for n in _nouns(rr):
                c = _score(pairs, ctx, n)
                if c > cands.get(n, (0, ''))[0]:
                    cands[n] = (c, rr)
        if not cands:
            continue
        ranked = sorted(cands.items(), key=lambda x: -x[1][0])
        best, (c1, r1) = ranked[0]
        c2 = ranked[1][1][0] if len(ranked) > 1 else 0
        if r1 in (cur, typed) or c1 < FIX_PAIR or c1 < RATIO * max(c2, 1):
            continue
        # 替えた行は今の行と並びの費用が同じくらいか軽く、置いた名詞が1語のまま読めること
        new = done[:t.start] + best + done[t.end:]
        base, cost = morphology.path_cost(done), morphology.path_cost(new)
        if base is None or cost is None or cost > base + COST_SLACK:
            continue
        if not any(x.start == t.start and x.end == t.start + len(best) and x.surface == best for x in tokenize(new)):
            continue
        out.append((t.start, t.end, best))
    return out


def repair_line(line, result, decided=(), input_method='kana'):
    if not isinstance(result, dict) or input_method != 'kana':
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(line, done)
    except Exception:
        return result
    if not marks:
        return result
    new = done
    details = []
    for s, e, rep in sorted(marks, reverse=True):
        new = new[:s] + rep + new[e:]
        details.append([done[s:e], rep, '1打の戻しの比べ直し'])
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    if any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
        return result
    out = dict(result)
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + details,
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
