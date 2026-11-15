# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""紫だけで止まる行のうち、「崩れたかなの並び」が残る行をその並びから読み直す（かな入力・2026-11-10・全体評価の手分け1）。

なぜ
----
紫の所の読み直し（odd_respell._repair_line）は、紫の所を語の区切りまで広げた読みに打ち違いの戻しを当てる。
紫が行の大半に掛かった行は読みが長すぎて（MAX_READ）何も試さず、紫が崩れた並びの一部（小書きの字だけ）に
掛かった行は語の読みが取れず、やはり何も試さない。紫が後ろの段で付く行は、読み直しの時点では紫が無い。
作った誤字の束では、紫が付いたのに正しい読みが1度も作られない行の多くがこの形だった。

どこを見るか
------------
小書きのかなが、付く先の無い字の後ろに在る並び（作った例: きょう を1キーずれて打った「くょう」の「くょ」）は、
正しい文には出ない。打ち違いの跡が確かに在る所なので、紫に掛かるかなの並びのうち、この跡を含む並びを
読み直す所にする。IME が前後を漢字にした形のために、打った読みの記録が在れば前か後ろの語1つまで広げた所も見る。

どうやって
----------
既存のファイルは変えない。install() が odd_respell._repair_line を外から包み、前からの読み直しが済んだ後に、
まだ残っている崩れた並びだけを見る。
1. 並びの読みに、手のずれの戻し（hand_shift・hand_shift_wide）・1キーの戻し（key_repairs）・1キーの戻しを
   2つ重ねた形を当てる。残すのは「跡が消える読み」だけ（付く先の無い小書きが残る読みは打つつもりの読みではない）。
   2キーまで見てよいのは、打ち違いが在ることと在る場所が跡で分かっているから。
2. 前からの置き方（odd_respell._placed）で漢字を置き、並びの費用の安い順に TOP 個だけ、前からの確かめ
   （odd_respell._judge: 補正に通して紫が残らないか）に通す。
3. 紫の残らない一番が、元の行より GAIN、二番より MARGIN 軽いときだけ採る（線は odd_respell のまま）。
   並べば直さない（紫のまま）。途中までの直し・つなぎ違い・変換を崩す形の守りも odd_respell のものを通す。
特定の語や文字列には合わせない。

切り替え: CN_PURPLE_NARROW=0 で前のまま。
"""
import os

TOP = 3             # 補正に通して確かめる形の数（1つごとに補正の通しが1〜2回）
MAX_READINGS = 250  # 漢字を置いてみる読みの数の上限（手のずれ・1キーを先に、2キーは残りの枠で）
MAX_RUNS = 2        # 1行で見る崩れた並びの数の上限
SIDE = 5            # 長い並びは、跡の前後これだけの字に絞る
NEIGHBOUR = 4       # 前後へ広げる語（かなでない並び）の字数の上限

_orig = {}
_BUSY = [False]
_MINE = {}          # 行 → この部品が決めた直し（yoon_slip に戻させないため）
STATS = {'lines': 0, 'readings': 0, 'judged': 0, 'fixed': 0}

_YOON_BASE = frozenset('きしちにひみりぎじぢびぴ')
_SMALL_YOON = frozenset('ゃゅょ')
_SMALL_VOWEL = {'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お'}
_ROWS = ('あかさたなはまやらわがざだばぱゃ', 'いきしちにひみりぎじぢびぴ', 'うくすつぬふむゆるぐずづぶぷゅ',
         'えけせてねへめれげぜでべぺ', 'おこそとのほもよろをごぞどぼぽょ')
_VOWEL_OF = {c: 'あいうえお'[k] for k, row in enumerate(_ROWS) for c in row}
_VOWEL_OF.update({c: c for c in 'あいうえお'})
# 外来の音の書き方（ふぁ・てぃ など）は跡と見ない
_LOAN = frozenset(('ふぁ', 'ふぃ', 'ふぇ', 'ふぉ', 'てぃ', 'でぃ', 'うぃ', 'うぇ', 'うぉ', 'しぇ', 'じぇ', 'ちぇ',
                   'つぁ', 'つぃ', 'つぇ', 'つぉ', 'とぅ', 'どぅ', 'ゔぁ', 'ゔぃ', 'ゔぇ', 'ゔぉ', 'でゅ', 'てゅ', 'ふゅ'))


def _on():
    return os.environ.get('CN_PURPLE_NARROW') != '0'


def _kana(c):
    return 'ぁ' <= c <= 'ゖ' or c in '゛゜ー'


def bad_small(text, i):
    """text[i] の小書きのかなが、前の字に付かない（打ち違いの跡）か。"""
    c = text[i]
    p = text[i - 1] if i else ''
    if c in _SMALL_YOON:
        return p not in _YOON_BASE and (p + c) not in _LOAN
    if c in _SMALL_VOWEL:
        if (p + c) in _LOAN:
            return False
        # 伸ばす書き方（なぁ・ねぇ・ー の後ろ）は跡と見ない
        if p == 'ー' or p in _SMALL_VOWEL or _VOWEL_OF.get(p) == _SMALL_VOWEL[c]:
            # ただし拗音の小書き（ゃゅょ）の後ろの同じ母音の小書きが、ー・っ・語の終わりでなく次のかなへ続くなら跡
            # （にゅぅりょく: う を打つつもりで ぅ。ぎゅぅっ・にゃぁ。 は伸ばす書き方のまま、2026-11-13 補正担当・
            # 未解決タブ）。CN_PN_YOON_LONG=0 で前のまま
            if p in _SMALL_YOON and os.environ.get('CN_PN_YOON_LONG') != '0':
                n = text[i + 1:i + 2]
                return bool(n) and 'ぁ' <= n <= 'ゖ' and n not in 'っぁぃぅぇぉ'
            return False
        return True
    return False


def garbled_runs(text, x, y):
    """紫 [x, y) に掛かるかなの並びのうち、打ち違いの跡（付く先の無い小書き）を含むもの [(開始, 終わり)]。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        if not _kana(text[i]):
            # かなでない字のすぐ後ろの小書きも跡（漢字＋ゃ）。次の並びの頭として拾う
            i += 1
            continue
        j = i
        while j < n and _kana(text[j]):
            j += 1
        if i < y and x < j:
            bad = [k for k in range(i, j) if bad_small(text, k) and (k > i or i > 0 or True)]
            if bad:
                a, b = i, j
                if b - a > 2 * SIDE:
                    a, b = max(i, bad[0] - SIDE), min(j, bad[-1] + SIDE + 1)
                out.append((a, b))
        i = j
    return out


def _reading(text, a, b):
    """並び [a, b) の打った読み: かなは字のまま、かなでない並びは打った読みの記録。取れなければ None。"""
    import odd_respell as O
    try:
        from kanji_guess import ime_readings_for
    except Exception:
        ime_readings_for = None
    parts = []
    i = a
    while i < b:
        k = _kana(text[i])
        j = i
        while j < b and _kana(text[j]) == k:
            j += 1
        if k:
            parts.append(O._hira(text[i:j]))
        else:
            got = [O._hira(r) for r in ((ime_readings_for(text[i:j]) if ime_readings_for else None) or ()) if r]
            got = [r for r in got if all(_kana(c) for c in r)]
            if not got:
                return None
            parts.append(got[0])
        i = j
    rd = ''.join(parts)
    return rd if rd and len(rd) <= O.MAX_READ else None


def _spans_to_try(cur, x, y):
    """[(開始, 終わり, 読み, 種類)]: 跡を含む並び（'run'）、前の語1つまで広げた所（'prev'）、後ろの語1つまで広げた所（'next'）。"""
    stop = '。、，．,.！？!?「」『』（）() 　\t'
    out = []
    for a, b in garbled_runs(cur, x, y):
        rd = _reading(cur, a, b)
        if rd:
            out.append((a, b, rd, 'run'))
        p = a
        while p > 0 and not _kana(cur[p - 1]) and cur[p - 1] not in stop and a - p < NEIGHBOUR:
            p -= 1
        if p < a and (p == 0 or _kana(cur[p - 1]) or cur[p - 1] in stop):
            rd = _reading(cur, p, b)
            if rd:
                out.append((p, b, rd, 'prev'))
        q = b
        while q < len(cur) and not _kana(cur[q]) and cur[q] not in stop and q - b < NEIGHBOUR:
            q += 1
        if q > b and (q == len(cur) or _kana(cur[q]) or cur[q] in stop):
            rd = _reading(cur, a, q)
            if rd:
                out.append((a, q, rd, 'next'))
    return out


def _clean(r):
    """跡の消えた読みか: ひらがなだけで、付く先の無い小書きが無く、小書き・ん・ー で始まらない。"""
    return bool(r) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in r) and r[0] not in 'ぁぃぅぇぉゃゅょっゎんー' \
        and not any(bad_small(r, i) for i in range(len(r)))


def repaired_readings(rd, before='', after=''):
    """並びの読み rd の、跡の消える戻し [(読み, 種類)]。種類: 'shift'（手のずれ）・'one'（1キー）・'two'（2キー）。"""
    from contextual_repair import key_repairs
    out, have = [], {rd}

    def add(r, kind):
        if r not in have and _clean(r):
            have.add(r)
            out.append((r, kind))
    try:
        import hand_shift
        for r in hand_shift.kana_repairs(rd):
            add(r, 'shift')
    except Exception:
        pass
    try:
        import hand_shift_wide
        for r in hand_shift_wide.shifted_readings(rd):
            add(r, 'shift')
    except Exception:
        pass
    ones = []
    for r in key_repairs(rd, before, after):
        r = getattr(r, 'reading', r)
        if r and r != rd and r not in ones:
            ones.append(r)
    for r in ones:
        add(r, 'one')
    for r1 in ones:
        if len(out) >= MAX_READINGS:
            break
        for r in key_repairs(r1, before, after):
            add(getattr(r, 'reading', r), 'two')
    return out[:MAX_READINGS]


def _kana_noun_left(field, fixed):
    """直した所に、かなで書いた名詞（2字以上）が残るか。打つつもりの読みなら IME は名詞を漢字か片仮名に変換する。
    かなのまま残るのは、置き方が決まらなかった読み（別の語の切れ端をつないだ形のことが多い）。"""
    import difflib
    from morphology import tokenize
    ops = [o for o in difflib.SequenceMatcher(None, field, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return False
    j1, j2 = ops[0][3], ops[-1][4]
    for t in tokenize(fixed):
        if not (t.start < j2 and j1 < t.end):
            continue
        # 形容詞のウ音便（〜しゅう）は今の文ではまず書かない形。崩れた並びの読み替えがこの形に落ちたものは採らない
        if t.pos == '形容詞' and getattr(t, 'infl_form', '') == '連用ゴザイ接続':
            return True
        if t.start < j2 and j1 < t.end and t.pos == '名詞' and len(t.surface) >= 2 \
                and all('ぁ' <= c <= 'ゖ' for c in t.surface) \
                and not (t.pos_sub or '').startswith(('非自立', '代名詞', '接尾', '副詞可能')):
            return True
    return False


def _unknown_kana_left(fixed, a):
    """直した形の、並びの頭 a に掛かる語が、辞書に無い かなだけの名詞（解析が未知語としてまとめた ぎにゅうりょくしたき）
    のままか。読み直しても語にならず、崩れた並びが残っている（2026-11-13 補正担当: 置いた形と並んで決まらなかった）。
    CN_PN_UNKNOWN_KANA=0 で前のまま。"""
    if os.environ.get('CN_PN_UNKNOWN_KANA') == '0':
        return False
    try:
        from morphology import tokenize
        import reading_lattice
        reading_lattice.load()
    except Exception:
        return False
    for t in tokenize(fixed):
        if t.start <= a < t.end or (a <= t.start < a + 2):
            if t.pos == '名詞' and len(t.surface) >= 3 and all('ぁ' <= c <= 'ゖ' for c in t.surface) \
                    and not reading_lattice._table.get(t.surface):
                return True
    return False


def _span_oks(field, a, b, rd, base, need, other_odd, run, store, dict_index, context_vec):
    """1つの所 [a, b)（読み rd）の、紫の残らない形 [(費用, 直した欄)]（安い順）。"""
    import odd_respell as O
    reps = repaired_readings(rd, field[:a][-1:], field[b:][:1])
    if not reps:
        return []
    STATS['readings'] += len(reps)
    rs = [r for r, _k in reps]
    src = {r: rd for r in rs}
    try:
        placed = O._placed(field, a, b, rs, store, dict_index, context_vec, src, set(rs) | {rd})
    except Exception:
        return []
    texts = list(dict.fromkeys(t for _c, t, _r in placed))
    cost = {}
    for c, t, _r in placed:
        cost.setdefault(t, c)
    if not texts or base - cost[texts[0]] < need:
        return []
    seen = {}
    for text in texts[:TOP]:
        oks = [v[0] for v in seen.values() if v[1]]
        if oks and cost[text] >= min(oks) + O.MARGIN:
            break       # 紫の残らない形が出て、次の形が置いた時点でそれより MARGIN 重いなら、残りは通さない
        STATS['judged'] += 1
        got = O._judge(field, a, b, [text], run, other_odd, True)
        for fx, v in got.items():
            if fx in got.further:
                continue            # 補正し直しがさらに別の所を直した形は、戻した形から遠い
            ok = v[1] and base - v[0] >= need and not _kana_noun_left(field, fx) and not _unknown_kana_left(fx, a) \
                and not any(bad_small(fx, i) for i in range(len(fx)) if 'ぁ' <= fx[i] <= 'ゖ') \
                and not (O._leftover_piece(field, fx, a, b) or O._bad_join(field, fx) or O._deconverted(field, fx)
                         or O._mark_replaced(field, fx))
            if fx not in seen or v[0] < seen[fx][0]:
                seen[fx] = (v[0], ok)
    return sorted((v[0], t) for t, v in seen.items() if v[1])


def _solve(field, runs, other_odd, run, store, dict_index, context_vec):
    """欄 field の崩れた並び runs = [(a, b, 読み, 種類)] から、直した欄か None。

    どの所の形も同じ場で比べ、一番が二番より MARGIN 軽ければ一番。並んだときは、後ろの語まで広げた所（'next'）だけ
    から来た形を外して、残りが1つならそれ（崩れた並びはふつう助詞で終わり、後ろの語は別の文節。後ろの正しい語まで
    替えた形とは、打った形に近いほうを採る）。前の語（IME が崩れた並びの頭を漢字にした所）まで広げた形は外さない。
    それでも決まらなければ None（紫のまま）。"""
    import morphology
    import odd_respell as O
    base = morphology.path_cost(field)
    if base is None:
        return None
    need = min(O.GAIN, O.GAIN_SHARE * base)
    pool = {}           # 形 → (費用, 後ろへ広げた所だけから来たか)
    for a, b, rd, kind in runs:
        for c, t in _span_oks(field, a, b, rd, base, need, other_odd, run, store, dict_index, context_vec):
            far = kind == 'next'
            if t not in pool:
                pool[t] = (c, far)
            else:
                pool[t] = (min(c, pool[t][0]), far and pool[t][1])
    if not pool:
        return None
    ranked = sorted((v[0], v[1], t) for t, v in pool.items())
    close = [x for x in ranked if x[0] - ranked[0][0] < O.MARGIN]
    if len(close) == 1:
        return close[0][2]
    near = [x for x in close if not x[1]]
    if len(near) == 1:
        return near[0][2]
    return None


def _repair_line(line, result, run, store, dict_index, context_vec=None, decided=(), input_method='kana'):
    fn = _orig['_repair_line']
    out = fn(line, result, run, store, dict_index, context_vec, decided, input_method)
    if _BUSY[0] or not _on() or input_method != 'kana' or not isinstance(out, dict):
        return out
    _BUSY[0] = True
    try:
        got = _after(line, out, run, store, dict_index, context_vec, decided)
        if got is out and (out.get('corrected') or line) != line and garbled_runs(line, 0, len(line)):
            # 前の段が崩れた並びを別の形に片付けていた行（小書きを大きくする・抜く など）は、打った行そのものからも
            # 読み直し、前の段の形よりはっきり自然（MARGIN 以上軽い）ならそちら。決まらなければ前のまま
            import morphology
            import odd_respell as O
            raw = dict(out)
            raw.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': []})
            got2 = _after(line, raw, run, store, dict_index, context_vec, decided)
            if got2 is not raw:
                c1 = morphology.path_cost(out.get('corrected'))
                c2 = morphology.path_cost(got2.get('corrected'))
                undone = False
                if '_yoon' in _orig:
                    # 前の段の形が、後ろの段（yoon_slip: 跡を前の字を替えずに片付けた直しは戻して紫）に戻される形なら、
                    # 比べる相手は打った行（紫だけ）。こちらで決まった形を採る
                    back = _orig['_yoon'](line, out, decided, input_method)
                    undone = back is not out and isinstance(back, dict) \
                        and bool(garbled_runs(back.get('corrected') or line, 0, len(back.get('corrected') or line)))
                if undone or (c1 is not None and c2 is not None and c2 + O.MARGIN <= c1):
                    got = got2
        if got is not out:
            if len(_MINE) > 200:
                _MINE.clear()
            _MINE[line] = got.get('corrected')
        return got
    except Exception:
        return out
    finally:
        _BUSY[0] = False


def _far_kana_respell(line, result, out, input_method):
    """この部品が決めた直しは、前の段の形からの遠さ（3打以上）で捨てない: 打った行からは2キーまでか手のずれ1つの
    戻しで、遠く見えるのは前の段が崩れた並びを別の形に片付けていたため。ほかの直しは前のまま。"""
    try:
        if _on() and isinstance(out, dict) and _MINE.get(line) and out.get('corrected') == _MINE.get(line):
            return False
    except Exception:
        pass
    return _orig['_far'](line, result, out, input_method)


def _yoon_repair_line(line, result, decided=(), input_method='kana'):
    """この部品が跡から読み直して決めた直しは、yoon_slip の「前の字を替えずに片付けた直しは戻す」に掛けない
    （手のずれ・2キーの戻しでは小書きの字そのものも替わる: 確かめの通しで紫が残らず、二番と離れて決まった形）。
    ほかの段の直し・ほかの所はそのまま yoon_slip が見る。"""
    fn = _orig['_yoon']
    try:
        mine = _MINE.get(line)
        done = result.get('corrected') if isinstance(result, dict) else None
        if mine and done and _on():
            import difflib
            keep = [(i1, max(i2, i1 + 1)) for tag, i1, i2, j1, j2 in
                    difflib.SequenceMatcher(None, line, mine, autojunk=False).get_opcodes()
                    if tag != 'equal' and mine[j1:j2] and mine[j1:j2] in done]
            if keep:
                # 小書きの字は替えた所の端に掛かることがあるので、前後1字まで守る
                keep = [(max(0, x - 1), y + 1) for x, y in keep]
                return fn(line, result, list(decided or ()) + keep, input_method)
    except Exception:
        pass
    return fn(line, result, decided, input_method)


def _in_name(line, ops):
    """直す所が、名前と見る所（敬称の前・@ の後ろ: correction_entry._name_spans）に掛かるか。名前は直さない決まり
    （後ろの段 _keep_names が戻して紫も外す）なので、ここでも手を付けない。"""
    if os.environ.get('CN_KEEP_NAMES') == '0':
        return False
    try:
        import correction_entry
        names = correction_entry._name_spans(line)
    except Exception:
        return False
    return any(x < max(o[2], o[1] + 1) and o[1] < y for o in ops for x, y in (names or ()))


def _after(line, out, run, store, dict_index, context_vec, decided):
    import difflib
    import odd_respell as O
    counted = False
    for _round in range(MAX_RUNS):
        cur = out.get('corrected') or line
        runs_all = garbled_runs(cur, 0, len(cur))
        if not runs_all:
            break
        if not counted:
            STATS['lines'] += 1
            counted = True
        new = None
        for ga, gb in runs_all[:MAX_RUNS]:
            fs, fe = O._field(cur, ga, gb)
            if not (fs <= ga and gb <= fe):
                continue
            field = cur[fs:fe]
            runs = [(a - fs, b - fs, rd, kind) for a, b, rd, kind in _spans_to_try(cur, ga, gb) if fs <= a and b <= fe]
            if not runs:
                continue
            lo, hi = min(r[0] for r in runs), max(r[1] for r in runs)
            others = set()
            for x0, y0 in (tuple(sp[:2]) for sp in (out.get('odd_spans') or ())):
                m = O._to_done(line, cur, x0, y0)
                if m and fs <= m[0] and m[1] <= fe and not (m[0] - fs < hi and lo < m[1] - fs):
                    others.add((m[0] - fs, m[1] - fs))
            fixed = _solve(field, runs, others, run, store, dict_index, context_vec)
            if not fixed:
                continue
            fixed = cur[:fs] + fixed + cur[fe:]
            try:
                import kana_keep as _kk
                fixed = _kk.wago_kana_respell(line, fixed)
            except Exception:
                pass
            try:
                if O._choice_overlaps(line, fixed):
                    continue
            except Exception:
                pass
            ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
            if not ops or any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
                continue
            if _in_name(line, ops):
                continue
            near = [(o[1], o[2]) for o in ops]
            # 崩れた並びに掛かっていた紫（行の大半に広がった紫も）は、確かめの通しで紫が残らなかったので外す
            back = O._map_spans(cur, line, [(ga, gb)]) if cur != line else [(ga, gb)]
            near += [tuple(x[:2]) for x in (back or ())]
            new = dict(out)
            new.update({'original': line, 'corrected': fixed, 'changed': True,
                        'details': list(out.get('details') or []) + [O._detail(cur, fixed)],
                        'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
            for key in ('odd_spans', 'unsure_spans'):
                new[key] = [sp for sp in (out.get(key) or ()) if not any(x < sp[1] and sp[0] < y for x, y in near)]
            if 'odd_reasons' in out:
                new['odd_reasons'] = [r for r in (out.get('odd_reasons') or ())
                                      if not any(x < r[1] and r[0] < y for x, y in near)]
            break
        if new is None:
            break
        STATS['fixed'] += 1
        out = new
    return out


def install():
    """包みを掛ける（もう掛かっていれば何もしない）。CN_PURPLE_NARROW=0 なら掛けない。"""
    if _orig or not _on():
        return bool(_orig)
    import odd_respell as O
    _orig['_repair_line'] = O._repair_line
    O._repair_line = _repair_line
    try:
        import yoon_slip
        _orig['_yoon'] = yoon_slip.repair_line
        yoon_slip.repair_line = _yoon_repair_line
    except Exception:
        pass
    try:
        import correction_entry
        _orig['_far'] = correction_entry._far_kana_respell
        correction_entry._far_kana_respell = _far_kana_respell
    except Exception:
        pass
    return True


def uninstall():
    if not _orig:
        return
    import odd_respell as O
    O._repair_line = _orig.pop('_repair_line')
    if '_yoon' in _orig:
        import yoon_slip
        yoon_slip.repair_line = _orig.pop('_yoon')
    if '_far' in _orig:
        import correction_entry
        correction_entry._far_kana_respell = _orig.pop('_far')
