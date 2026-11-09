# -*- coding: utf-8 -*-
"""かな入力で濁点・半濁点のキーを隣の字に付けてしまった所を戻す（2026-11-08 補正担当: はじめる を ばしめる と打って
ば占める・未解決タブの書き足しの型）。

打った読み（記録・無ければ辞書の読み）の、漢字の語とその前のかなの語をつないだ窓で、゛゜ を1つだけ隣の字へ動かした
読みを辞書の表記にする。動かした行の費用が元の行より MARGIN 以上軽く、置く語が身近（COMMON 以下）なら置く。
2つ以上の動かし方が並べば置かない（紫は他の段に任せる）。語を名指しした表は持たない。かな入力だけ。CN_DAKUTEN_SHIFT=0 で使わない。
"""
import os
import unicodedata

MARGIN = 3000
COMMON = 450
_MARKS = '゙゚'


def on():
    return os.environ.get('CN_DAKUTEN_SHIFT') != '0'


def _compose(seq):
    s = unicodedata.normalize('NFC', seq)
    if any(c in _MARKS for c in s) or any(c in '゛゜' for c in s):
        return None              # 付けられない字に付いた
    return s


def shifts(reading, with_pos=False):
    """reading の ゛゜ を1つ、前か後ろの字へ動かした読み。with_pos なら (読み, 元の字の位置, 付け先の位置)
    （位置は reading の字の番号）。"""
    chars = list(reading)
    out = []
    for i, ch in enumerate(chars):
        d = unicodedata.normalize('NFD', ch)
        if len(d) != 2 or d[1] not in _MARKS:
            continue
        for j in (i - 1, i + 1):
            if j < 0 or j >= len(chars):
                continue
            t = unicodedata.normalize('NFD', chars[j])
            if len(t) != 1:
                continue
            new_t = _compose(t + d[1])
            if not new_t or len(new_t) != 1:
                continue
            v = chars[:]
            v[i] = d[0]
            v[j] = new_t
            v = ''.join(v)
            if v != reading and v not in [x[0] for x in out]:
                out.append((v, i, j))
    return out if with_pos else [x[0] for x in out]


def propose(text):
    """[(開始, 終了, 置く表記 or None)]。"""
    try:
        import ime_reconvert as R
        from morphology import path_cost
    except Exception:
        return []
    rv = R.typed_reverse(text)
    if not rv:
        return []
    phon, words = rv
    base_cost = path_cost(text)
    if base_cost is None:
        return []
    out = []
    n = len(words)
    for k in range(n):
        s, e, rs, re_, pos, src = words[k]
        if not any('一' <= ch <= '鿿' for ch in text[s:e]):
            continue
        spans = [(k, k)]
        if k > 0 and words[k - 1][5] == 'kana' and words[k - 1][4] != '記号' and words[k - 1][1] == s:
            spans.append((k - 1, k))
        if k + 1 < n and words[k + 1][5] == 'kana' and words[k + 1][4] != '記号' and words[k + 1][0] == e:
            spans.append((k, k + 1))
        cands = []
        for a, b in spans:
            ws, we = words[a][0], words[b][1]
            rd = phon[words[a][2]:words[b][3]]
            if not any(c in _MARKS for c in unicodedata.normalize('NFD', rd)):
                continue
            cut = words[a][3] - words[a][2]        # 窓の読みで、前の語の終わり
            kanji_unit = [any('一' <= ch <= '鿿' for ch in text[w[0]:w[1]]) for w in (words[a], words[b])]
            for v, i, j in shifts(rd, with_pos=True):
                # 漢字の語の読みの濁り（題 の だ）を、隣のかなの語へ移す形（く題 → 具体）は採らない: 濁った読みで
                # 漢字を選んでいる
                ui, uj = (0 if i < cut else 1), (0 if j < cut else 1)
                if a != b and ui != uj and kanji_unit[ui] and not kanji_unit[uj]:
                    continue
                # 1つの漢字の語の読みの中だけで動かす形（告 を つげ と読んで 続け）は採らない: その読みは IME が
                # 1語として返した字の読みで、濁点の付け違いなら語が割れて出る
                if (ui == uj or a == b) and kanji_unit[ui if a != b else 0]:
                    continue
                line, sc = R.dict_convert(text, ws, we, v, path_cost=path_cost, keep=False, scored=True)
                if sc is None or line == text:
                    continue
                c = path_cost(line)
                if c is None or c > base_cost - MARGIN:
                    continue
                d = len(line) - len(text)
                face = line[ws:we + d]
                if not any('一' <= ch <= '鿿' for ch in face) or R._rank(face) > COMMON and _verb_rank(face) > COMMON:
                    continue
                if not _one_word(face) or not _reads(face, v):
                    continue
                cands.append((c, ws, we, face))
        if not cands:
            continue
        cands.sort()
        best = cands[0]
        if len({x[3] for x in cands if x[0] - best[0] < MARGIN}) > 1:
            # 動かし方が並ぶときは置かない（紫は元の段に任せる: いつ告ったの のような正しい行に紫を足さない）
            continue
        else:
            out.append((best[1], best[2], best[3]))
    # 重なるものは軽い方だけ
    res = []
    for x in out:
        if not any(y[0] < x[1] and x[0] < y[1] for y in res):
            res.append(x)
    return res


def _reads(face, v):
    """置く表記が、動かした読みそのままに読めるか（公地 の くぢ を ぐち と読み替えて 口 を置かない）。"""
    try:
        from morphology import tokenize
        rd = ''.join(t.reading or t.surface for t in tokenize(face))
        rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in rd)
        return rd == v
    except Exception:
        return False


def _one_word(face):
    """置く表記が内容の語1つ（＋活用の尾・助動詞）か（近場所・行こじ のような語の組は採らない）。"""
    try:
        from morphology import tokenize
        toks = list(tokenize(face))
    except Exception:
        return False
    content = [t for t in toks if t.pos not in ('助動詞', '助詞') and not (t.pos == '動詞' and t.pos_sub == '非自立')]
    if not (len(content) == 1 and toks[0] is content[0] and getattr(content[0], 'has_reading', True)):
        return False
    # 尾の助動詞は今の言葉の活用だけ（行こ｜じ の古い じ は採らない）
    return all(t.surface in _AUX for t in toks if t.pos == '助動詞')


_AUX = ('た', 'だ', 'ます', 'まし', 'ませ', 'です', 'でし', 'ない', 'なかっ', 'ぬ', 'ん', 'う', 'よう', 'れる', 'れ',
        'られる', 'られ', 'せる', 'せ', 'させる', 'させ', 'たい', 'たく', 'たかっ')


def _verb_rank(face):
    """活用した表記（始めた）は、終止形に戻した語の身近さで見る。"""
    try:
        import ime_reconvert as R
        from morphology import tokenize
        toks = list(tokenize(face))
        heads = [t for t in toks if t.pos in ('動詞', '形容詞', '名詞')]
        if not heads:
            return 800
        return max(R._rank(getattr(t, 'base_form', None) or t.surface) for t in heads)
    except Exception:
        return 800


def repair_line(line, result, decided=(), input_method='kana'):
    import difflib
    if not on() or input_method != 'kana' or not isinstance(result, dict):
        return result
    text = result.get('corrected') or line
    try:
        props = propose(text)
    except Exception:
        return result
    props = [p for p in props if not any(a < p[1] and p[0] < b for a, b in decided)]
    if not props:
        return result
    new = text
    odd = [list(o) for o in (result.get('odd_spans') or [])]
    fixes = []
    for s, e, face in sorted(props, reverse=True):
        if face is None:
            if [s, e] not in odd:
                odd.append([s, e])
            continue
        fixes.append((text[s:e], face))
        new = new[:s] + face + new[e:]
        odd = [o for o in odd if not (o[0] < e and s < o[1])]
    out = dict(result)
    if new != text:
        # 紫は直した後の行の位置へ（直した所より後ろはずらす）
        ops = difflib.SequenceMatcher(None, text, new, autojunk=False).get_opcodes()
        def mv(i):
            for tag, i1, i2, j1, j2 in ops:
                if i1 <= i <= i2:
                    return j1 + min(i - i1, j2 - j1)
            return i
        odd = [[mv(a), mv(b)] for a, b in odd]
        ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out['corrected'] = new
        out['changed'] = True
        out['spans'] = [[o[3], o[4]] for o in ops2]
        out['original_spans'] = [[o[1], o[2]] for o in ops2]
        out['details'] = list(result.get('details') or []) + [(a, b, 'かな入力の濁点の付け違い') for a, b in fixes]
    out['odd_spans'] = odd
    return out
