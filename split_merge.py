# -*- coding: utf-8 -*-
"""身近な語が3つ以上に割れた所を、1打の戻しで1語（身近な語の組）にまとめる候補（2026-11-09 手分けA）。

うにさんの決まり（2026-11-09）: かな入力の ゛ は1つのキー。「余分な ゛」とは見ない。゛ の付いた字は、゛ を意図して押した
（元の字だけが隣のキーの打ち違い）と見て、゛ を保ったまま元の字を隣のキーの字に替える。ローマ字入力は字ごとの1打違い
（corrector.adjacent_slip の romaji）で見る。
- 読み: 割れた語ごとの読み（1字の漢字は字の音訓も: 歳=さい／とし）。
- 候補: 読みの1字を1打戻した読みが、身近な語1つ、または身近な語＋身近な語（接尾の 化・的 なども）に変換できる表記。
correction_entry._unknown_word_guard が、入口の直し（知られていない漢字の並びへの直し）を戻すかどうかに使う。
特定の語には合わせない。CN_SPLIT_MERGE=0 で使わない。
"""
import itertools
import os

COMMON = 470
_HIRA = [chr(c) for c in range(0x3041, 0x3097)]
_VOICED = dict(zip('かきくけこさしすせそたちつてとはひふへほ', 'がぎぐげござじずぜぞだぢづでどばびぶべぼ'))
_DEVOICE = {v: k for k, v in _VOICED.items()}


def on():
    return os.environ.get('CN_SPLIT_MERGE') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def variants(r, input_method='kana'):
    """読み r の1字を1打だけ戻した読み。かな入力は ゛ を保つ。"""
    import corrector
    out = set()
    for i, c in enumerate(r):
        if input_method == 'kana':
            base = _DEVOICE.get(c, c)
            for b in _HIRA:
                if b == base or not corrector.adjacent_slip(base, b, 'kana'):
                    continue
                if c in _DEVOICE:
                    b = _VOICED.get(b)
                    if not b:
                        continue
                out.add(r[:i] + b + r[i + 1:])
        else:
            for b in _HIRA:
                if b != c and corrector.adjacent_slip(c, b, 'romaji'):
                    out.add(r[:i] + b + r[i + 1:])
    return out


def faces(r):
    """読み r を身近な語1つか、身近な語2つの組にした表記。"""
    import ime_reconvert as R
    ok = lambda f: any(_kanji(c) for c in f) and R._rank(f) <= COMMON
    got = {f for f in R._dict_faces(r) if ok(f)}
    for k in range(1, len(r)):
        a = [f for f in R._dict_faces(r[:k]) if ok(f) and all(_kanji(c) for c in f)]
        if not a:
            continue
        b = [f for f in R._dict_faces(r[k:]) if ok(f) and all(_kanji(c) for c in f)]
        for x in a[:2]:
            for y in b[:2]:
                if _reads_back(x + y, r):
                    got.add(x + y)
    return got


def _reads_back(face, r):
    """組にした表記 face が、読み r のとおりに読まれるか（解析の読みをつないで r になる）。
    IME は打った読みで変換する。組の片方を珍しい読みで引いた表記（出｜家 を いで｜いえ と読む）は、その読みを打っても
    IME が返さないので候補にしない（2026-11-09 手分けA）。CN_SPLIT_MERGE_READBACK=0 で前のまま（見ない）"""
    if os.environ.get('CN_SPLIT_MERGE_READBACK') == '0':
        return True
    try:
        import morphology
        ts = list(morphology.tokenize(face))
        return bool(ts) and all(t.has_reading for t in ts) and _hira(''.join(t.reading for t in ts)) == r
    except Exception:
        return True


def readings(tokens):
    """割れた語の並びの読みの候補（1字の漢字は字の音訓も、多くて16通り）。"""
    opts = []
    for t in tokens:
        rs = [_hira(t.reading)] if t.has_reading else [t.surface]
        if len(t.surface) == 1 and _kanji(t.surface):
            try:
                import ime_order
                rs += [x for x in ime_order.readings_of(t.surface) if x not in rs]
            except Exception:
                pass
        opts.append(rs[:4])
    return [''.join(x) for x in itertools.islice(itertools.product(*opts), 16)]


def candidates(tokens, input_method='kana'):
    """割れた語の並びを1打の戻しでまとめた表記の集まり。"""
    out = set()
    for r in readings(tokens):
        for v in variants(r, input_method):
            out |= faces(v)
    return out
