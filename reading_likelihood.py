# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""原文の読みを前後の3文字で測る。候補生成・履歴保存は行わない。

同梱表は文章と重み付き語彙の混合であり、日本語全体の確率ではない。
未観測の並びは診断材料。正しい語・活用・複合語も未観測になり得るので、
この値だけから異様と断定しない。設計/反証: GPT-6、2026-09-11。
"""
from dataclasses import dataclass, asdict
from functools import lru_cache
from itertools import product
import math
from typing import Optional


def _kana(text):
    return ''.join(chr(ord(c)-96) if 'ァ' <= c <= 'ヶ' else c for c in text)


def _reading(text):
    return bool(text) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)


@dataclass(frozen=True)
class Window:
    start: int
    gram: str
    count: int
    forward_total: int
    backward_total: int
    forward_probability: Optional[float]
    backward_probability: Optional[float]

    @property
    def unlikely(self):
        # 未観測に加えて、少なくとも一方の文脈自体には十分な材料が必要。
        return (self.count == 0 and max(self.forward_total, self.backward_total) >= 4096)


@lru_cache(maxsize=1)
def _distributions():
    from ngram_yomi import TRIGRAMS
    forward = {}; backward = {}
    alphabet = set()
    for gram, count in TRIGRAMS.items():
        if len(gram) != 3 or not _reading(gram):
            continue
        forward[gram[:2]] = forward.get(gram[:2], 0)+count
        backward[gram[1:]] = backward.get(gram[1:], 0)+count
        alphabet.update(gram)
    return forward, backward, max(1, len(alphabet))


def windows(reading, start=0, end=None):
    """指定範囲に重なる全3連。対象字が末尾/中央/先頭になる窓を含む。

前向きは P(3字目|前2字)、後ろ向きは P(1字目|後2字)。
分母も別に集計する。文脈未登録は None（確率0と区別）。
読み文字単位の位置であり、濁音はここでは1字、物理キー分解とは別。
"""
    from ngram_yomi import TRIGRAMS
    end = len(reading) if end is None else end
    if not 0 <= start <= end <= len(reading):
        raise ValueError('reading range outside text')
    if start == end:
        return ()
    forward, backward, vocab = _distributions()
    out = []
    for i in range(max(0, start-2), min(end, len(reading)-2)):
        gram = reading[i:i+3]
        if not _reading(gram):
            continue
        count = TRIGRAMS.get(gram, 0)
        a, b = forward.get(gram[:2], 0), backward.get(gram[1:], 0)
        out.append(Window(i, gram, count, a, b,
                          (count+1)/(a+vocab) if a else None,
                          (count+1)/(b+vocab) if b else None))
    return tuple(out)


def local_cost(reading, start=0, end=None):
    """対象に重なる窓の双方向の平均負対数。材料がなければ None。"""
    values = [-math.log(p) for w in windows(reading, start, end)
              for p in (w.forward_probability, w.backward_probability) if p is not None]
    return sum(values)/len(values) if values else None


def edit_cost(original, revised, before='', after=''):
    """変わる読み位置と、その前後2字を使った候補側の費用。

変わらない語尾の長さで平均を薄めない。同じ読みの表記違いも同じ値。
削除では消えた字の両側が新しく接する窓だけを含める。
"""
    start = 0
    while start < min(len(original), len(revised)) and original[start] == revised[start]:
        start += 1
    if original == revised:
        return local_cost(before[-2:]+revised+after[:2], len(before[-2:]), len(before[-2:])+len(revised))
    tail = 0
    while (tail < min(len(original), len(revised))-start
           and original[-1-tail] == revised[-1-tail]):
        tail += 1
    left = before[-2:]
    full = left+revised+after[:2]
    a, b = len(left)+start, len(left)+len(revised)-tail
    ws = windows(full, a, b) if a < b else tuple(
        w for w in windows(full) if w.start < a < w.start+3)
    values = [-math.log(p) for w in ws
              for p in (w.forward_probability, w.backward_probability) if p is not None]
    return sum(values)/len(values) if values else None


def adjacent_readings(text, tokens, start, end):
    """編集範囲の外の連続した読み。空白・不明・語途中を越えない。"""
    before = ''; after = ''; cursor = start
    for t in reversed([t for t in tokens if t[4] <= start]):
        if t[4] != cursor: break
        options, _ = _options(t)
        if len(options) != 1: break
        before = options[0]+before; cursor = t[3]
        if len(before) >= 2: break
    cursor = end
    for t in tokens:
        if t[3] < end: continue
        if t[3] != cursor: break
        options, _ = _options(t)
        if len(options) != 1: break
        after += options[0]; cursor = t[4]
        if len(after) >= 2: break
    return before[-2:], after[:2]


def _options(token, dictionary_alternatives=True):
    import kanji_guess
    saved = tuple(dict.fromkeys(r for r in kanji_guess.ime_readings_for(token[0]) if _reading(r)))
    if saved:
        return saved, 'saved_ime_pair'
    literal = _kana(token[0])
    if _reading(literal):
        return (literal,), 'literal_kana'
    if len(token) > 5 and token[5] and _reading(token[2]):
        from inflected_lexicon import dictionary_readings
        others = list(dictionary_readings(token[0])) if dictionary_alternatives else []
        return tuple(dict.fromkeys([token[2]] + others)), 'dictionary_word'
    # 異様の診断段階で、未知漢字へ一字ずつ推測の読みを当てない。
    return (), 'unreadable'


def evidence(text, tokens, dictionary_alternatives=True):
    """原文から読めた範囲だけを測る。空白・未知漢字・記号を越えない。

位置は原文へ対応させる。漢字語内部の読み位置を漢字一字へ比例配分しない。
複数読みがある場合、どの読みでも不一致になる境界だけ supported=True。
"""
    parts = [tuple(t) for t in tokens if len(t) >= 6
             and 0 <= t[3] < t[4] <= len(text) and text[t[3]:t[4]] == t[0]]
    opts = [_options(t, dictionary_alternatives) for t in parts]
    rd = ''; owners = []; previous_end = None
    for i, t in enumerate(parts):
        choices, origin = opts[i]
        if previous_end is not None and previous_end != t[3]:
            rd += '|'; owners.append(None)
        segment = choices[0] if choices else '|'
        rd += segment; owners.extend([i if choices else None]*len(segment))
        previous_end = t[4]
    # IMEが複数の解析語にまたがっていても、原解析の読みで上書きしない。
    # 読み長が違うときに漢字数へ比例配分すると誤った境界を指すので、
    # この場合は全範囲の診断に留め、語境界が裏付けられたとは扱わない。
    import kanji_guess
    whole = [r for r in kanji_guess.ime_readings_for(text) if _reading(r)]
    if whole and whole[0] != rd:
        return [dict(asdict(w), source_start=0, source_end=len(text),
                     surfaces=[text], reading_sources=['saved_ime_pair'],
                     internal=None, supported=False, alignment='whole_ime_span')
                for w in windows(whole[0]) if w.unlikely]
    out = []
    for w in windows(rd):
        if not w.unlikely:
            continue
        ids = sorted(set(owners[w.start:w.start+3]))
        first, last = ids[0], ids[-1]
        ts = parts[first:last+1]
        # 語内部の珍しさは誤りの証拠にしない。境界の外来語・人名も
        # 表記の頻度だけでは判断しないので、単独の異様理由にはしない。
        supported = first != last
        alternatives = 1
        for i in ids: alternatives *= len(opts[i][0])
        if alternatives > 64:
            supported = False
        elif supported:
            # 別読みで境界を説明できるなら、原解析1本の低確率で断定しない。
            for variants in product(*(opts[i][0] for i in ids)):
                joined = ''.join(variants)
                boundaries = []; offset = 0
                for r in variants[:-1]: offset += len(r); boundaries.append(offset)
                cross = [v for v in windows(joined)
                         if any(v.start < p < v.start+3 for p in boundaries)]
                if not any(v.unlikely for v in cross):
                    supported = False
                    break
        out.append(dict(asdict(w), source_start=ts[0][3], source_end=ts[-1][4],
                        surfaces=[t[0] for t in ts], reading_sources=[opts[i][1] for i in ids],
                        internal=first == last, supported=supported))
    return out


def nominal_slot_spans(text, tokens):
    """名詞＋終止形＋格助詞を、読み境界の不一致と合わせて調べる。

終止形＋名詞（連体修飾）は対象にしない。既知の複合動詞・名詞の
別解を保ち、助詞の省略だけでも断定しない。未観測の3連が同じ
名詞/動詞境界をまたぐ場合に、分割が崩れた可能性を異様として扱う。
"""
    from inflected_lexicon import has_nominal_entry, dictionary_readings
    candidates = []
    for i in range(len(tokens)-2):
        a, b, c = tokens[i:i+3]
        if (min(len(a), len(c)) < 6 or len(b) < 7 or not a[5] or not b[5] or a[4] != b[3] or b[4] != c[3]
                or a[1] not in ('名詞:一般', '名詞:サ変接続')
                or b[1] != '動詞:自立' or b[6] != '基本形'
                or c[0] != 'を' or not c[1].startswith('助詞:格助詞')):
            continue
        if i and tokens[i-1][4] == a[3] and not tokens[i-1][1].startswith(('助詞', '記号')):
            continue
        body = text[a[3]:b[4]]
        if dictionary_readings(body) or has_nominal_entry(b[0]):
            continue
        # この判定には品詞と活用の不整合が既にある。文中で得た読み
        # （IMEがあれば優先）を測り、無関係な品詞用法の別読みに差し替えない。
        rows = evidence(body, [tuple(t[:3])+(t[3]-a[3],t[4]-a[3])+tuple(t[5:]) for t in (a,b)], dictionary_alternatives=False)
        if any(r['supported'] for r in rows):
            from morphology import allows_bare_clause_object
            if allows_bare_clause_object(text[c[4]:]):
                continue
            candidates.append((a[0], b[0]+c[0], a[3], c[4]))
    return candidates
