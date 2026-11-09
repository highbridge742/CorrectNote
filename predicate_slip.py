# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
述語の打ち違いが IME で辞書の語に変換され、異様の印が立たない所を、例文の組と一般の語の表で見る段
（predicate_slip・2026-11-01 B。うにさん 11-01「漢字変換を挟むと補正されません」）。

とりかかる を さりかかる と打つと IME は 去り＋かかる（動詞＋補助の動詞）を出す。名詞＋する の読みを打ち違えると、
IME は意味の無い名詞の並び＋する を出すことがある。どちらも辞書の語の並びなので紫が付かず、並びの費用もほとんど
軽くならない（取り掛かる の形で 300〜3,000）。決め手は語の表:

  - 元の述語（去りかかる・名詞の並び＋する）は一般の語の表（wordfreq）にも例文（Tatoeba）にも無い。
  - 打った読みを戻した読み（隣のキー・巻き込みの抜き・抜け・二度押し・入れ替わり。1打、無ければ2打）に漢字を置くと、
    1語の述語（取り掛かる・サ変の名詞＋する）になり、その語は一般の語の表に在る。

直すのは、戻した述語が例文で前と同じ助詞と組になっていて（に＋取り掛かる）、候補が1つのときだけ。
例文に組が無い・候補が2つ以上並ぶときは紫。元の述語が表に在れば何もしない。かな入力だけ。
特定の語や文字列には合わせない。
"""
import difflib
import gzip
import json
import os
from functools import lru_cache

COMMON = 640      # 戻した述語（動詞・サ変の名詞）が一般の語の表でこれ以下（大きいほど稀）
PAIR_MIN = 2      # 直すのは、戻した述語が例文で前の助詞と組になった回数がこれ以上のとき
COST_SLACK = 1500
PURPLE_GAIN = 5000  # 名詞の並び＋する を紫にするのは、戻した形がこれだけ軽いとき  # 戻した行が元の行よりこれ以上重くなるなら採らない
MAX_READ = 12
# サ変の名詞＋する に戻した形で、する の後ろに残してよいかな（する の活用に付く助動詞・て だけ。し＋いて のような動詞は残さない）
SAHEN_TAILS = ('', 'ます', 'ました', 'ません', 'て', 'た', 'ない', 'たい')
SECOND_FROM = 8
_CONTRACTED = frozenset(('てる', 'でる', 'とく', 'どく', 'ちゃう', 'じゃう', 'てく', 'でく'))
PARTICLES = ('を', 'に', 'で', 'が', 'は', 'と', 'へ', 'から', 'まで')


def _here(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


@lru_cache(maxsize=1)
def _wordfreq():
    # ja_wordfreq.json.gz は ime_reconvert の読み込みを共有する（解析の子1つで1回だけ読む）。
    try:
        from ime_reconvert import _freq
        return _freq() or None
    except Exception:
        return None


@lru_cache(maxsize=1)
def _pairs():
    """(助詞, 述語) → 例文の回数・述語 → 回数・名詞 → 回数。サ変の名詞＋する は 続\t名詞\tする から 名詞する。"""
    try:
        with gzip.open(_here('tatoeba_pairs.json.gz'), 'rt', encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        return None
    pv, v_all = {}, {}
    for k, c in d['pairs'].items():
        parts = k.split('\t')
        if len(parts) != 3:
            continue
        p, n, v = parts
        if p == '続' and v == 'する':
            v_all[n + 'する'] = v_all.get(n + 'する', 0) + c
            continue
        pv[(p, v)] = pv.get((p, v), 0) + c
        v_all[v] = v_all.get(v, 0) + c
    return pv, v_all, d.get('nouns') or {}


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _sub(t):
    return (getattr(t, 'pos_sub', '') or '').split(':')[0]


def _runs(toks, fresh=()):
    """[(最初の字句, 最後の字句, 元の述語の形, 'verb'|'suru')]。
    verb: 漢字を含む自立の動詞＋すぐ後ろの非自立の動詞（去り＋かかる）。
    suru: 漢字の名詞が2つ以上すき間なく並び＋する。
    fresh: 前の段がこの行で直した所（直した行の位置）。そこに出た かなの動詞＋動詞（2か所の打ち違いの1か所だけを
    戻して、かなの動詞の並びが残った形）も verb として見る。"""
    out = []
    n = len(toks)
    for i, t in enumerate(toks):
        if (fresh and t.pos == '動詞' and _sub(t) == '自立' and _all_hira(t.surface) and i + 1 < n
                and any(x < t.end and t.start < y for x, y in fresh)):
            j = i
            while (j + 1 < n and toks[j + 1].start == toks[j].end and toks[j + 1].pos == '動詞'
                   and _all_hira(toks[j + 1].surface)):
                j += 1
            if j > i:
                out.append((i, j, ''.join(x.surface for x in toks[i:j]) + (toks[j].base_form or toks[j].surface),
                            'verb'))
                continue
        if t.pos == '動詞' and _sub(t) == '自立' and any(_kanji(c) for c in t.surface):
            j = i
            while j + 1 < n and toks[j + 1].start == toks[j].end and (
                    (toks[j + 1].pos == '動詞' and _sub(toks[j + 1]) == '非自立')
                    or (j == i and toks[j + 1].pos == '連体詞' and _all_hira(toks[j + 1].surface)
                        and toks[j + 1].surface[-1:] in 'うくぐすつぬぶむる')):
                # 補助の動詞が後ろの名詞に付いて連体詞に切れた形（去り＋かかる＋予定）も同じ
                j += 1
            if j == i + 1 and toks[j].pos == '動詞' and toks[j].base_form in _CONTRACTED \
                    and os.environ.get('CN_PREDICATE_CONTRACTED') != '0':
                # ている・ておく・てしまう の縮まった形（動い＋てる・書い＋とく・食べ＋ちゃう）は話し言葉の正しい形。
                # 打ち違いの述語と見ない（2026-11-05 うに「解決していたものが戻った」）
                continue
            if (j == i and j + 1 < n and toks[j + 1].start == toks[j].end and toks[j + 1].pos == '動詞'
                    and _all_hira(toks[j + 1].surface) and (t.infl_form or '').startswith('連用')
                    and os.environ.get('CN_PS_TAIL_VERB') != '0'):
                # 漢字の動詞の連用形＋かなの動詞が自立に切れた形（取れ＋かかる＋。）も、動詞＋補助の動詞と同じに見る
                j += 1
            if j > i:
                form = ''.join(x.surface for x in toks[i:j]) + (toks[j].base_form or toks[j].surface)
                out.append((i, j, form, 'verb'))
        if (t.pos == '名詞' and len(t.surface) == 1 and _kanji(t.surface) and 0 < i and i + 2 < n
                and toks[i - 1].pos == '助詞' and toks[i - 1].end == t.start
                and toks[i + 1].pos == '助詞' and len(toks[i + 1].surface) == 1 and toks[i + 1].start == t.end
                and toks[i + 2].pos == '動詞' and _sub(toks[i + 2]) == '自立' and toks[i + 2].start == toks[i + 1].end
                and not (i + 3 < n and toks[i + 3].pos == '動詞' and toks[i + 3].start == toks[i + 2].end)
                # 名詞＋格助詞＋動詞（家｜に｜いました・手｜を｜洗う）はふつうの文の形。動詞に直に続けられない の の時だけ見る
                # （家にいました → 構いました にしていた・2026-11-09 補正担当）。CN_PS_KANJI_PIECE_NO=0 で前のまま
                and (toks[i + 1].surface == 'の' or os.environ.get('CN_PS_KANJI_PIECE_NO') == '0')
                and os.environ.get('CN_PS_KANJI_PIECE') != '0'):
            # 助詞の後ろの 1字の漢字の名詞＋1字の助詞＋動詞（に｜都｜の｜掛かる）: 動詞の読みの1打違いを IME が
            # 1字の名詞と助詞に切った跡かもしれない。直すのは下の決まり（例文で前の助詞と組・候補1つ）のときだけ
            out.append((i, i + 2, ''.join(x.surface for x in toks[i:i + 2]) + (toks[i + 2].base_form or toks[i + 2].surface),
                        'verb'))
        if t.pos == '名詞' and all(_kanji(c) for c in t.surface):
            # 漢字の名詞にかなの助動詞が付いて、すぐかなの動詞が続く形（名詞＋れ＋かかる: 名詞に れ は付かない）
            j = i + 1
            while j < n and toks[j].pos == '助動詞' and _all_hira(toks[j].surface) and toks[j].start == toks[j - 1].end:
                j += 1
            if (j > i + 1 and j < n and toks[j].pos == '動詞' and _sub(toks[j]) == '自立' and _all_hira(toks[j].surface)
                    and toks[j].start == toks[j - 1].end):
                out.append((i, j, ''.join(x.surface for x in toks[i:j]) + (toks[j].base_form or toks[j].surface), 'verb'))
            # 1字の漢字の名詞が2つ以上すき間なく並び、すぐ漢字の動詞が続く形（1字ずつの名詞に
            # 切れるのは、読みが語にならず IME が字ごとに当てた跡）。2字以上の名詞（ご飯＋食べる: 助詞の省き）は見ない
            if i == 0 or not (toks[i - 1].pos == '名詞' and toks[i - 1].end == t.start):
                j = i
                while (j < n and toks[j].pos == '名詞' and len(toks[j].surface) == 1 and _kanji(toks[j].surface)
                       and (j == i or toks[j].start == toks[j - 1].end)):
                    j += 1
                if (j >= i + 2 and j < n and toks[j].pos == '動詞' and _sub(toks[j]) == '自立'
                        and any(_kanji(c) for c in toks[j].surface) and toks[j].start == toks[j - 1].end):
                    out.append((i, j, ''.join(x.surface for x in toks[i:j]) + (toks[j].base_form or toks[j].surface),
                                'verb'))
        if t.pos == '名詞' and _sub(t) == 'サ変接続' and all(_kanji(c) for c in t.surface) and i + 1 < n \
                and toks[i + 1].start == t.end:
            # サ変の名詞のすぐ後ろに する 以外の自立の動詞（印刷＋居て）か、する の連用形＋漢字の自立の動詞（確認＋し＋舞う）:
            # サ変の名詞に動詞は直に付かない・し＋動詞 は辞書に無ければ IME が する の後ろの打ち違いを別の動詞にした跡
            u = toks[i + 1]
            if (u.pos == '動詞' and _sub(u) == '自立' and u.base_form != 'する' and any(_kanji(c) for c in u.surface)
                    and not _ime_first_verb(u)):
                out.append((i, i + 1, t.surface + (u.base_form or u.surface), 'sahen'))
            elif (u.pos == '動詞' and u.base_form == 'する' and u.surface == 'し' and i + 2 < n
                  and toks[i + 2].start == u.end and toks[i + 2].pos == '動詞' and _sub(toks[i + 2]) == '自立'
                  and any(_kanji(c) for c in toks[i + 2].surface)):
                out.append((i, i + 2, t.surface + 'し' + (toks[i + 2].base_form or toks[i + 2].surface), 'sahen'))
        if t.pos == '名詞' and all(_kanji(c) for c in t.surface) and (i == 0 or not (
                toks[i - 1].pos == '名詞' and toks[i - 1].end == t.start)):
            j = i
            while (j + 1 < n and toks[j + 1].pos == '名詞' and all(_kanji(c) for c in toks[j + 1].surface)
                   and toks[j + 1].start == toks[j].end):
                j += 1
            if j > i and j + 1 < n and toks[j + 1].pos == '動詞' and toks[j + 1].base_form == 'する' \
                    and toks[j + 1].start == toks[j].end:
                out.append((i, j + 1, ''.join(x.surface for x in toks[i:j + 1]) + 'する', 'suru'))
    return out


def _ime_first_verb(u):
    """動詞の基本形が、その読みで IME が先頭に返す身近な語か（編集｜押す: おす の先頭は 押す）。そうなら、サ変の名詞の
    すぐ後ろでも助詞を省いた正しい形（ボタンの名前＋押す）として打ち違いと見ない。IME の先頭でない字（印刷｜居て:
    いる の先頭は 入る）は今のまま見る（2026-11-08 未解決タブの誤判定・ime_order の考え）。CN_PS_IME_FIRST=0 で前のまま。"""
    if os.environ.get('CN_PS_IME_FIRST') == '0':
        return False
    base = u.base_form or u.surface
    rd = _hira(getattr(u, 'reading', '') or '')
    if not base or not rd:
        return False
    try:
        import ime_reconvert as R
        # 基本形の読み: この字句の読みから送り仮名を外した語幹＋基本形の送り仮名（居｜い → いる。居る を読み直すと おる）
        k = len(u.surface)
        while k > 0 and not _kanji(u.surface[k - 1]):
            k -= 1
        kb = len(base)
        while kb > 0 and not _kanji(base[kb - 1]):
            kb -= 1
        tail_s, tail_b = u.surface[k:], base[kb:]
        if tail_s and not rd.endswith(_hira(tail_s)):
            return False
        brd = rd[:len(rd) - len(tail_s)] + _hira(tail_b)
        faces = [f for f in R._dict_faces(brd, 40) if any(_kanji(c) for c in f)]
        if not faces:
            return False
        top = min(faces, key=lambda f: (R._rank(f), faces.index(f)))
        if not (top == base and R._rank(base) <= 500):
            return False
        # 名詞を を で取る動詞（押す・使う）だけ: 助詞を省いた形（編集｜押す）になれる。取らない動詞（散歩｜死ぬ）は
        # 打ち違いの見込みのまま
        import semantic_fit as F
        pr = F.profile('を', base)
        return bool(pr) and len(pr) >= 10
    except Exception:
        return False


def _known(form, wf, v_all, nouns):
    if form in wf or v_all.get(form, 0):
        return True
    stem = form[:-2] if form.endswith('する') else None
    return bool(stem and (stem in wf or nouns.get(stem, 0)))


def _predicate_at(text, a):
    """text の a から始まる1語の述語 → (述語の形, 終わり) か None。動詞（自立で、後ろに非自立の動詞が続かない）か、
    漢字の名詞1語＋する。"""
    from morphology import tokenize
    toks = list(tokenize(text))
    for k, t in enumerate(toks):
        if t.start != a:
            continue
        u = toks[k + 1] if k + 1 < len(toks) else None
        if t.pos == '動詞' and _sub(t) == '自立':
            if u is not None and u.pos == '動詞' and u.start == t.end:
                return None
            return t.base_form or t.surface, t.end
        if (t.pos == '名詞' and _sub(t) == 'サ変接続' and all(_kanji(c) for c in t.surface) and u is not None
                and u.pos == '動詞' and u.base_form == 'する' and u.start == t.end):
            return t.surface + 'する', u.end
        return None
    return None


@lru_cache(maxsize=4096)
def _sahen(surface):
    from morphology import tokenize
    toks = list(tokenize(surface + 'する'))
    return len(toks) == 2 and toks[0].surface == surface and _sub(toks[0]) == 'サ変接続'


def _expand(rds, left, right, tried):
    from contextual_repair import key_repairs
    reps = []
    for rd in rds:
        for r in key_repairs(rd, left, right):
            r = getattr(r, 'reading', r)
            if r and r not in tried and len(r) <= MAX_READ:
                tried.add(r)
                reps.append(r)
    return reps


def _suru_candidates(done, a, b, rds, wf, suffix='する'):
    """名詞＋する の戻し。戻した読みの する の前を読みの表（reading_lattice）で引き、サ変の名詞で一般の語の表に在る
    ものを置く（_place_kanji は ちゃくしゅする に漢字を置けないことがある）。1打で無ければ2打。"""
    import reading_lattice
    import morphology
    reading_lattice.load()
    tried = set(rds)
    level = [r for r in rds if r.endswith(suffix)]
    for _depth in range(2):
        level = _expand(level, done[:a][-1:], done[b:][:1], tried)
        out = []
        for r in level:
            if not r.endswith(suffix) or len(r) < len(suffix) + 2:
                continue
            for sf, _l, _r, _c, pos in reading_lattice._table.get(r[:-len(suffix)], ()):
                if pos != '名詞' or not all(_kanji(c) for c in sf) or wf.get(sf, 10 ** 6) > COMMON or not _sahen(sf):
                    continue
                text = done[:a] + sf + suffix + done[b:]
                c = morphology.path_cost(text)
                if c is not None:
                    out.append((sf + 'する', text, c))
        if out:
            return out
    return []


def _candidates(done, a, b, rds, store, dict_index, context_vec, wf, kind='verb', tail=''):
    """[(述語の形, 漢字を置いた行, 費用)]。1打の戻しで1つも無ければ2打。"""
    import odd_respell as O
    if kind == 'suru':
        # する の活用した形（し・さ・せ）は、その字のまま後ろに残す
        return _suru_candidates(done, a, b, rds, wf, done[:b][-1:] if done[:b][-1:] in 'しさせす' else 'する')
    tried = set(rds)
    level = list(rds)
    for _depth in range(2):
        reps = _expand(level, done[:a][-1:], done[b:][:1], tried)
        out = []
        placed = O._placed(done, a, b, reps, store, dict_index, context_vec)
        for c, text, r in placed:
            got = _predicate_at(text, a)
            if not got:
                continue
            form, end = got
            stop = len(text) - (len(done) - b)
            # 述語は戻した所の終わりまで（後ろに残してよいのは、元の述語の後ろの助動詞のかなだけ: 始め＋た）
            if not (end <= stop and (text[end:stop] == tail or (
                    kind == 'sahen' and text[end:stop] in SAHEN_TAILS))):
                continue
            stem = form[:-2] if form.endswith('する') else form
            if wf.get(stem, 10 ** 6) > COMMON:
                continue
            out.append((form, text, c))
        if out:
            return out
        # 2打目は、1打戻して漢字を置いた行の費用の安い順に SECOND_FROM だけから広げる
        level = [r for _c, _t, r in placed[:SECOND_FROM]]
    return []


def _all_hira(s):
    return all('ぁ' <= c <= 'ゖ' for c in s)


def _org_span(line, done, a, b):
    """直した行の [a, b) に当たる元の行の所。前の段が直した所に掛かれば、その直しの元の所ごと広げる。"""
    if done == line:
        return a, b
    lo = hi = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
        if j2 <= a and not (j1 == j2 == a) or j1 >= b and not (j1 == j2 == b):
            continue
        if tag == 'equal':
            x, y = i1 + max(a, j1) - j1, i1 + min(b, j2) - j1
        else:
            x, y = i1, i2
        lo = x if lo is None else min(lo, x)
        hi = y if hi is None else max(hi, y)
    if lo is None or lo >= hi:
        return None
    return lo, hi


def repair_line(line, result, run, store, dict_index, context_vec=None, decided=(), input_method='kana'):
    """result: 行のほかの補正の答え。run(text): 後段を通さない補正。"""
    if not isinstance(result, dict) or input_method != 'kana':
        return result
    wf = _wordfreq()
    tab = _pairs()
    if not wf or not tab:
        return result
    pv, v_all, nouns = tab
    import morphology
    import odd_respell as O
    done = result.get('corrected') or line
    toks = list(morphology.tokenize(done))
    fresh = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
             if o[0] != 'equal'] if done != line else []
    runs = _runs(toks, fresh)
    if not runs:
        return result
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    out = result
    for i, j, form, kind in sorted(runs, key=lambda x: -x[0]):
        if _known(form, wf, v_all, nouns):
            continue
        cur = out.get('corrected') or line
        if cur != done:
            break       # 前の所を直した後は位置がずれる。残りは次の解析で
        a, b = toks[i].start, toks[j].end
        org = _org_span(line, done, a, b)
        if org is None or any(x < org[1] and org[0] < y for x, y in (decided or ())):
            continue
        # 後ろの助動詞のかな（た・ます）も読みに含める（動詞の語幹だけの読みでは、同じ読みの名詞が置かれる）
        k = j
        while kind in ('verb', 'sahen') and k + 1 < len(toks) and toks[k + 1].pos == '助動詞' and _all_hira(toks[k + 1].surface) \
                and toks[k + 1].start == toks[k].end and toks[k + 1].end - a < MAX_READ:
            k += 1
        tail = done[b:toks[k].end]
        b = b_ext = toks[k].end
        span = O._span_reading(done, a, b, dict_index)
        if span is None:
            continue
        sa, sb, rds = span
        if sa != a or sb < b:
            # 打った読みの記録が前の字から始まる（前の1字から1度に確定した所）なら、その所ごと戻す
            if not (sa <= a and sb >= b):
                continue
            a, b = sa, sb
        base = morphology.path_cost(done)
        if base is None:
            continue
        attempts = [(a, b, rds)]
        # 前に助詞が2つ続き、すぐ前が1字（に＋と＋動詞…）: その1字は打ち違いの巻き込みかもしれないので、含めた読みも見る
        k = next((x for x in range(len(toks)) if toks[x].end == a), None)
        if (k is not None and k >= 1 and toks[k].pos == '助詞' and len(toks[k].surface) == 1
                and _all_hira(toks[k].surface) and toks[k - 1].pos == '助詞' and toks[k - 1].end == toks[k].start):
            attempts.append((toks[k].start, b, [toks[k].surface + r for r in rds]))
        forms, strong, first = {}, [], None
        for x0, y0, rd0 in attempts:
            cands = _candidates(done, x0, y0, rd0, store, dict_index, context_vec, wf, kind, tail)
            cands = [x for x in cands if x[2] <= base + COST_SLACK]
            if not cands:
                continue
            k = next((x for x in range(len(toks)) if toks[x].end == x0), None)
            p = toks[k].surface if k is not None and toks[k].pos == '助詞' else None
            fs = {}
            for f, text, c in cands:
                if f not in fs or c < fs[f][1]:
                    fs[f] = (text, c)
            st = [f for f in fs if p and pv.get((p, f), 0) >= PAIR_MIN]
            if kind == 'sahen':
                # サ変の名詞はそのまま残り、後ろが する に戻るだけの形（印刷＋居て → 印刷＋して）は、名詞の語を替えない
                # 1打の戻しなので、それ1つなら決める（名詞＋する は例文の組の表に無い）
                st = [f for f in fs if f == toks[i].surface + 'する']
            if first is None:
                first = (fs, st, x0, y0)
            if st:
                forms, strong, a, b = fs, st, x0, y0
                break
        else:
            if first is None:
                continue
            forms, strong, a, b = first
        if not forms:
            continue
        if (a, b) != (toks[i].start, b_ext):
            org2 = _org_span(line, done, a, b)
            if org2 is None or any(x < org2[1] and org2[0] < y for x, y in (decided or ())):
                continue
            org = org2
        fixed = None
        if len(strong) == 1 and len(forms) <= 2:
            text = forms[strong[0]][0]
            try:
                g = run(text)
            except Exception:
                g = None
            if isinstance(g, dict):
                got = g.get('corrected') or text
                spans = [tuple(sp[:2]) for sp in list(g.get('odd_spans') or ()) + list(g.get('unsure_spans') or ())]
                lo, hi = a, a + len(got) - (len(done) - b)
                if not any(x < hi and lo < y for x, y in spans) and not O._splits_kanji_run(done, got, a, b):
                    fixed = got
        if fixed and fixed != done:
            ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
            if not ops or any(x < o[2] and o[1] < y for o in ops for x, y in (decided or ())):
                continue
            near = [(o[1], o[2]) for o in ops]
            new = dict(out)
            new.update({'original': line, 'corrected': fixed, 'changed': True,
                        'details': list(out.get('details') or []) + [O._detail(done, fixed)[:2] + ['述語の打ち違い']],
                        'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
            for key in ('odd_spans', 'unsure_spans'):
                new[key] = [sp for sp in (out.get(key) or ()) if not any(x < sp[1] and sp[0] < y for x, y in near)]
            if 'odd_reasons' in out:
                new['odd_reasons'] = [r for r in (out.get('odd_reasons') or ())
                                      if not any(x < r[1] and r[0] < y for x, y in near)]
            out = new
            continue
        # 決め手が無い: 紫（もう紫なら何もしない）。動詞＋補助の動詞（言い＋かける・泣き＋出す）は辞書に無くてもふつうに
        # 作れる形なので、例文の組の在る候補が並ぶときだけ。名詞の並び＋する は、戻した形が PURPLE_GAIN 以上軽いときだけ
        if any(x < org[1] and org[0] < y for x, y in odd_now):
            continue
        if kind in ('verb', 'sahen') and not strong:
            continue
        if kind == 'suru' and base - min(c for _t, c in forms.values()) < PURPLE_GAIN:
            continue
        new = dict(out)
        new['odd_spans'] = sorted(set(odd_now) | {org})
        new['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (org[0], org[1], f'「{line[org[0]:org[1]]}」は辞書に無い述語です。1打違いの「{"・".join(sorted(forms)[:3])}」かもしれません')]
        odd_now.append(org)
        out = new
    return out
