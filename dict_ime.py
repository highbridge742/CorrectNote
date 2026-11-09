# -*- coding: utf-8 -*-
"""IME の読み取りの口（ime_language.JapaneseIME）と同じ形で、打った記録と辞書だけで答える代わり（2026-11-07）。

うに「打った記録があれば読みに戻す変換は必要ない」「候補は IME でなく辞書から」。IME の無い環境（雲）で、
最初の変換を使う段（ime_spelling.project_first_words・contextual_repair の同音の述語）が呼ばれるようにする。

- convert_words(読み): 読みの格子（reading_lattice）の切り方で、語ごとに同じ読みの辞書の表記を当て、
  行の費用（morphology.path_cost）＋身近さ（ja_wordfreq の段）が一番よいものを選ぶ。助詞・助動詞はかなのまま。
  2語をつないだ読みが1語として在れば（seed_japanese.is_unit）その表記も比べる。
- reverse_words(表記): ime_reconvert.typed_reverse（打った記録、無ければ辞書の読み）。
- phonetic(表記): reverse_words の読み。
本物の IME の候補一覧（SearchCandidates）は持たない。特定の語には合わせない。
"""
from functools import lru_cache

DICT_TOP = 8
RANK_W = 15
KANA_RANK = 520
KATA_MARGIN = 50
_KEEP_KANA_POS = ('助詞', '助動詞', '記号', 'フィラー', '感動詞')


def _strong(s):
    return any('一' <= c <= '鿿' or 'ァ' <= c <= 'ヶ' for c in s)


def _rank(face):
    import ime_reconvert
    return ime_reconvert._rank(face)


def _line_score(line):
    from morphology import path_cost, tokenize
    c = path_cost(line)
    if c is None:
        return None
    ranks = [0]
    for t in tokenize(line):
        if not _strong(t.surface):
            if t.pos in ('名詞', '動詞', '形容詞'):
                ranks.append(KANA_RANK)
            continue
        if t.pos in ('助詞', '助動詞', '記号'):
            continue
        face = getattr(t, 'base_form', '') if t.pos in ('動詞', '形容詞') else t.surface
        ranks.append(_rank(face or t.surface))
    # 内容の語ごとの身近さを足す（語ごとに表記を選ぶので、1語の差がそのまま効くように）
    return c + RANK_W * sum(ranks)


@lru_cache(maxsize=4096)
def _convert(reading):
    import ime_reconvert as R
    import reading_lattice
    if not reading:
        return None
    try:
        res = reading_lattice.best(reading)
    except Exception:
        return None
    if not res.words or any(w[2] == '未知' for w in res.words):
        return None
    words = [[w[0] if w[2] not in _KEEP_KANA_POS else w[1], w[1], w[2]] for w in res.words]
    # かなの語（読みのまま）は、格子の表記が漢字なら候補に入る。語ごとに表記を選び直す（左から1回ずつ）
    for i, (face, key, pos) in enumerate(words):
        if pos in _KEEP_KANA_POS:
            continue
        opts = list(dict.fromkeys([face] + list(R._dict_faces(key, DICT_TOP)) + [key]))
        # 片仮名の表記は、同じ読みの漢字の表記がどれも KATA_MARGIN 以上珍しいときだけ（パン・カエル は採り、
        # 猫→ネコ・降り→フリ は採らない。IME は和語を漢字かかなで書く）
        kanji = [_rank(o) for o in opts if any('一' <= c <= '鿿' for c in o)]
        opts = [o for o in opts if not (all('ァ' <= c <= 'ヶ' or c == 'ー' for c in o) and kanji
                                       and min(kanji) < _rank(o) + KATA_MARGIN)] or [key]
        if len(opts) == 1:
            continue
        best, best_sc = face, None
        for o in opts:
            if o != key and not R._plausible_face(o, o):
                continue
            line = ''.join(w[0] if j != i else o for j, w in enumerate(words))
            sc = _line_score(line)
            if sc is not None and (best_sc is None or sc < best_sc):
                best, best_sc = o, sc
        words[i][0] = best
    # 隣り合う2語の読みが1語として在れば（報告｜書 → 報告書）、その表記も比べる
    try:
        import seed_japanese
        unit = seed_japanese.is_unit
    except Exception:
        unit = lambda f: None
    i = 0
    while i + 1 < len(words):
        a, b = words[i], words[i + 1]
        if a[2] in _KEEP_KANA_POS or b[2] in _KEEP_KANA_POS:
            i += 1
            continue
        here = ''.join(w[0] for w in words)
        here_sc = _line_score(here)
        cands = [f for f in R._dict_faces(a[1] + b[1], DICT_TOP) if unit(f) is not False]
        # 語ごとの表記の組のうち1語として在るもの（ほうこく＋しょ → 報告書）
        cands += [x + y for x in R._dict_faces(a[1], DICT_TOP) for y in R._dict_faces(b[1], DICT_TOP)
                  if unit(x + y) is True]
        best = None
        for f in dict.fromkeys(cands):
            line = ''.join(w[0] for w in words[:i]) + f + ''.join(w[0] for w in words[i + 2:])
            sc = _line_score(line)
            if sc is not None and here_sc is not None and sc < here_sc and (best is None or sc < best[1]):
                best = (f, sc)
        if best:
            words[i:i + 2] = [[best[0], a[1] + b[1], a[2]]]
        else:
            i += 1
    first, out, at, rs = '', [], 0, 0
    for face, key, pos in words:
        out.append((at, at + len(face), rs, rs + len(key), 0, 0))
        first += face
        at += len(face)
        rs += len(key)
    return first, tuple(out)


class DictIME:
    """JapaneseIME の読み取りの口のうち convert・convert_words・reverse_words・phonetic だけ。"""
    available = True

    def __init__(self, strict=False):
        # strict: 記録が証す変換だけを答える（IME の判定の入口 ime_inverse_gate 用。辞書の変換が原文と同じになるのは
        # 証拠にならない）
        self.strict = strict
        # 打った記録が読みを証す表記: 読み → 表記（reverse_words で記録だけから読めた表記）。IME はその読みから
        # その表記を出したので、convert(その読み) はその表記を返す（雲でも「IME の最初の変換が原文と同じ」が言える）
        self._attested = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def convert_words(self, reading):
        """(最初の変換の表記, ((表記の開始, 終了, 読みの開始, 終了, 0, 0), ...))。IME の convert_words と同じ形。
        strict なら打った記録が証す表記だけ（語の区切りはその表記の打った記録から）。"""
        if self.strict:
            surface = self._attested.get(reading)
            if not surface:
                return None
            got = self.reverse_words(surface)
            return (surface, got[1]) if got and got[0] == reading else None
        return _convert(reading)

    def convert(self, reading):
        if reading in self._attested:
            return self._attested[reading]
        if self.strict:
            return None
        got = _convert(reading)
        return got[0] if got else None

    def reverse_words(self, surface):
        import ime_reconvert
        try:
            got = ime_reconvert.typed_reverse(surface)
        except Exception:
            return None
        if got and any(w[5] == 'typed' for w in got[1]) and all(
                w[5] in ('typed', 'kana') for w in got[1]):
            self._attested[got[0]] = surface
        return got

    def phonetic(self, surface):
        got = self.reverse_words(surface)
        return got[0] if got else None

