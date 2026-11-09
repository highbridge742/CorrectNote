# -*- coding: utf-8 -*-
"""morphology.path_cost の速い版（答えは janome と同じ。2026-11-08 挙動関連担当）。

path_cost は「その並びをいちばん自然に読んだときの不自然さ」＝ janome の最小コストの道の、最後の語の min_cost。
1行の補正で数千回呼ばれ、子の時間の約4割を占めていた（40行の測りで 73,672回・81秒中32秒）。janome は
語の並びを作るために、位置ごとの語（Node）を作り、前の語すべてとの連接コストを1つずつ引く。答えに要るのは
コストの最小値だけなので、ここでは
  ・前の語を「右の文脈 ID ごとの最小コスト」にまとめる（最小値は、同じ右 ID の中では一番安いものしか効かない）
  ・同じ位置で同じ左 ID の語は、連接の最小を1回だけ計算する
  ・辞書引き（50字の窓）の答えを控える（候補の文字列は同じ後ろ半分を何度も引く）
だけを変えた。語の候補の作り方（辞書・未知語・forward の飛び方）は janome の __tokenize_partial と同じ手順。
最後の語の選び方（EOS の同点の扱い: 辞書の語どうしは番号の小さい方）も janome と同じにしてある。

長い行（janome が区切って解く 500字超）と、janome の作りが想定と違うときは、元の path_cost に任せる。
"""
import threading

_INF = 2147483647
_LOOKUP = {}
_LOOKUP_LIMIT = 20000
_ok = None
_original = None
# The dictionary window: janome looks up 50 characters, but no word is longer than the longest entry, so the
# words found depend only on that many characters (a shorter key finds the same window again more often).
# Measured for janome 0.5.0's IPAdic (392,127 entries, the longest 26 characters); any other dictionary: 50.
_KNOWN_LONGEST = {('0.5.0', 392127): 26}
_WINDOW = 50


def _setup(tokenizer):
    global _ok
    try:
        d = tokenizer.sys_dic
        ok = (getattr(tokenizer, 'user_dic', None) is None and hasattr(d, 'connections') and hasattr(d, 'unknowns')
              and callable(getattr(d, 'get_char_categories', None)) and hasattr(tokenizer, 'matcher')
              and getattr(type(tokenizer), 'MAX_CHUNK_SIZE', None) == 1024 and getattr(type(tokenizer), 'CHUNK_SIZE', None) == 500)
    except Exception:
        ok = False
    _ok = bool(ok)
    global _WINDOW
    _WINDOW = 50
    if _ok:
        try:
            import importlib.metadata as metadata
            count = sum(len(index['positions']) for _mm, index in d.entries_compact.values())
            _WINDOW = min(50, _KNOWN_LONGEST.get((metadata.version('janome'), count), 50))
        except Exception:
            _WINDOW = 50
    return _ok


def _lookup(window, d, matcher):
    got = _LOOKUP.get(window)
    if got is None:
        got = tuple((len(e[1]), e[2], e[3], e[4], e[0]) for e in d.lookup(window.encode('utf-8'), matcher))
        if len(_LOOKUP) >= _LOOKUP_LIMIT:
            for k in [k for _, k in zip(range(len(_LOOKUP) // 2), _LOOKUP)]:
                del _LOOKUP[k]
        _LOOKUP[window] = got
    return got


def min_cost(text, tokenizer):
    """The min_cost of the last token janome gives for this (already stripped) text. Raises _Fails where janome's
    tokenize would raise (path_cost then answers None, as it does for janome's errors)."""
    n = len(text)
    d = tokenizer.sys_dic; matcher = tokenizer.matcher; conn = d.connections
    cats = d.get_char_categories; unknowns = d.unknowns
    max_unknown = tokenizer.max_unknown_length
    window = _WINDOW
    ends = [None] * (n + 2)
    ends[0] = {0: 0}                  # BOS: right id 0, cost 0
    finals = []                       # nodes ending at n, in janome's order: (min_cost, right_id, num or None)
    pos = 0
    while pos < n:
        prev = ends[pos]
        best_left = {}
        nodes = list(_lookup(text[pos:pos + window], d, matcher))
        matched = len(nodes) > 0
        cates = cats(text[pos])
        if cates:
            for cate in cates:
                if matched and not d.unknown_invoked_always(cate):
                    continue
                length = d.unknown_length(cate) if not d.unknown_grouping(cate) else max_unknown
                size = 1
                for p in range(pos + 1, min(n, pos + length + 1)):
                    _cates = cats(text[p])
                    if cate in _cates or any(cate in compat for compat in _cates.values()):
                        size += 1
                    else:
                        break
                for left, right, cost, _pos in unknowns.get(cate):
                    nodes.append((size, left, right, cost, None))
        for length, left, right, cost, num in nodes:
            m = best_left.get(left)
            if m is None:
                m = _INF
                for r, c in prev.items():
                    v = c + conn[r][left]
                    if v < m: m = v
                best_left[left] = m
            # janome: the min starts at INF - cost, and nothing below it leaves no best node (it raises)
            if m >= _INF - cost:
                raise _Fails
            mc = m + cost
            e = pos + length
            slot = ends[e]
            if slot is None:
                ends[e] = {right: mc}
            else:
                old = slot.get(right)
                if old is None or mc < old: slot[right] = mc
            if e == n:
                finals.append((mc, right, num))
        pos += 1
        while pos <= n and not ends[pos]:
            pos += 1
        if pos > n:
            raise _Fails               # janome walks off the end of its lattice (IndexError)
    # EOS (left id 0): the first strictly smaller; a tie between two dictionary words goes to the smaller number
    best = None; m = _INF
    for mc, right, num in finals:
        v = mc + conn[right][0]
        if v < m:
            m, best = v, (mc, num)
        elif v == m and best is not None and best[1] is not None and num is not None and num < best[1]:
            m, best = v, (mc, num)
    if best is None:
        raise _Fails
    return best[0]


class _Fails(Exception):
    pass


def install(morphology):
    """Put the fast path_cost in morphology (same cache, same lock, same answers). Returns True when installed."""
    global _original
    if getattr(morphology.path_cost, '_fast', False):
        return True
    if not getattr(morphology, 'HAS_JANOME', False) or morphology._TOKENIZER is None:
        return False
    tokenizer = morphology._TOKENIZER
    if not _setup(tokenizer):
        return False
    original = _original = morphology.path_cost
    lock = morphology._TOKENIZE_LOCK

    def path_cost(line):
        if not line:
            return None
        cache = morphology._COST_CACHE
        got = cache.get(line)
        if got is not None:
            return got
        text = line.strip()
        if not text or len(text) > 500:
            return original(line)
        try:
            with lock:
                cost = min_cost(text, tokenizer)
        except _Fails:
            return None
        except Exception:
            return original(line)
        if len(cache) >= morphology._COST_CACHE_LIMIT:
            cache.clear()
        cache[line] = cost
        return cost
    path_cost._fast = True
    path_cost.__doc__ = original.__doc__
    path_cost.__wrapped__ = original
    morphology.path_cost = path_cost
    return True
