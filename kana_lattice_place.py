# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
かなのまま残った並びの「区切り」を読みの格子（reading_lattice・同梱辞書の読み＋連接）で決め、
表記は今までの置き方（last_keystroke._kanji_choices の候補・身近さの門）に任せる（補正担当・2026-10-25。
うにさん 06:13Z「右に書かれた平仮名も漢字に変換されない」、「新しい手を検討」スレッドの手1）。

守ること（「新しい手を検討」06:31Z）:
  - 既に漢字のある所は格子で替えない。かなだけの並びの中だけ。
  - 格子の費用は格子の中の差（1番と2番の切り方）にしか使わない。行の自然さ（morphology.path_cost）とは混ぜない。
  - 区切りに迷う（1番と2番の費用が近い）所は置かずに紫。
特定の語を名指ししない。reading_lattice が無ければ何もしない。
"""
import difflib
import os

MIN_RUN = 3            # 見るかなの並びの長さ（字）
MIN_WORD = 2           # 置く語の読みの長さ
SEG_MARGIN = 800       # 1番と2番の切り方の費用の差がこれ未満なら迷い（紫）
_CONTENT_POS = ('名詞',)   # 置く語は名詞だけ（動詞・形容詞のかなは書くつもりのかなが多い: ひいて・こされ・ふせ。2026-10-25 測り）


KATA_COMMON = 470   # 片仮名で置く外来語の身近さ（wordfreq の段）


def _hira(ch):
    return 'ぁ' <= ch <= 'ゖ' or ch == 'ー'


def _kanji(ch):
    return '一' <= ch <= '鿿' or ch == '々'


def kana_runs(text):
    """[(start, end)] かなだけの並び（MIN_RUN 以上）。"""
    out = []
    i = 0
    while i < len(text):
        if _hira(text[i]):
            j = i
            while j < len(text) and _hira(text[j]):
                j += 1
            if j - i >= MIN_RUN:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


COMMON_FACE = 470      # ime_reconvert._rank がこれ以下の表記（一般の文章でよく使う）だけ置く
_COPULA = ('だ', 'です', 'でし', 'だっ', 'で', 'じゃ')
OTHER_FACE = 600       # 同じ読みのほかの表記がこれ以下なら、どちらか決まらない


def _everyday_faces(rd, store, dict_index, LK):
    """読み rd の表記のうち、今までの置き方の門（本人の語・表に無い2字の漢語は置かない）を通るもの。"""
    try:
        faces = LK._kanji_choices(rd, store, dict_index)
    except Exception:
        faces = []
    own = _own_kept(rd, set(LK._own_faces(rd, store)))
    got = [f for f in faces if f in own or (not LK._not_everyday_kango(f) and LK._kango_reads_as(f, rd))]
    # 頭の 御 と お・ご だけが違う表記（御辞儀・お辞儀）は同じ語の書き方の違い。迷いに数えず、一般によく使う方だけ残す
    # （おじぎした が紫になっていた・2026-11-09 正しい文の試し）。CN_LATTICE_HONORIFIC_SAME=0 で前のまま
    if os.environ.get('CN_LATTICE_HONORIFIC_SAME') != '0':
        got = [f for f in got if not (f.startswith('御') and len(f) > 1
                                      and any(g != f and g[1:] == f[1:] and g[0] in 'おご' for g in got))]
    return got, own


def _own_kept(rd, own):
    """本人の語の表記のうち、置いてよいもの。辞書が平仮名でも書く名詞（うどん）を、一般の文章でほとんど使わない漢字の
    表記（饂飩）にする本人の語は外す（2026-11-03 うに 優先の行: 本人の語彙に入った珍しい表記で、平仮名で打った語が
    替わっていた。使うほど直しが崩れない・うに 10-22）。"""
    import os
    if not own or os.environ.get('CN_OWN_RARE_FACE') == '0':
        return own
    try:
        import ime_reconvert
        import reading_lattice
        reading_lattice.load()
        rows = reading_lattice._table.get(rd, ())
    except Exception:
        return own
    if not any(len(r) > 4 and r[0] == rd and r[4] == '名詞' for r in rows):
        return own
    return {f for f in own if ime_reconvert._rank(f) <= OTHER_FACE}


def _kana_noun_ok(rd, prev='', nxt=''):
    """かなで書く名詞（こと・もの・ところ・とき・これ・いちばん）か。並びの中に在っても、ほかの名詞を置くのを止めない
    （2026-11-05 挙動関連担当の PC の測り: 用言＋かなの名詞＋助詞＋用言 の行が漢字にならない）。CN_LATTICE_KANA_NOUN=0。
    前後の語（の｜ところ｜で）と一緒に解析して、その位置の語の種類で見る（ところ・もの は1語だけでは 一般 になる）。"""
    if os.environ.get('CN_LATTICE_KANA_NOUN') == '0':
        return False
    try:
        from morphology import tokenize
    except Exception:
        return False
    subs = ('非自立', '代名詞', '副詞可能', '数')
    # 用言の後ろの そう・よう（きれ｜そう: 助動詞の語幹）もかなで書く語。CN_LATTICE_KANA_AUXSTEM=0
    if os.environ.get('CN_LATTICE_KANA_AUXSTEM') != '0':
        subs = subs + ('助動詞語幹',)
    for p, q in ((prev, nxt), ('', '')):
        try:
            toks = list(tokenize(p + rd + q))
        except Exception:
            continue
        at = [t for t in toks if t.start == len(p) and t.end == len(p) + len(rd)]
        if at and at[0].pos == '名詞' and any(k in (at[0].pos_sub or '') for k in subs):
            return True
    return False


def _explained_nouns(a, spans, store, dict_index, LK, before='', doubts=None):
    """かなの文法で説明の付く並びの中の、漢字で書くのが普通の名詞だけを置く → [(start, end, 表記)]。
    形式名詞・代名詞（こと・もの・これ）・副詞（だいたい・いちばん）・形容動詞の語幹（きれい）、用言・助詞はかなのまま。
    格子は区切りにだけ使い、表記は今までの置き方の候補から選ぶ（格子の表記は 良吏・御宇 のような珍しい語のことがある）:
      - 続く名詞をつないだ読みが辞書の1語で、門を通る表記が1つだけ（ぎょう＋ばんごう → 行番号）ならそれ。
      - 1語なら、門を通る表記のうち一般の文章でよく使う（COMMON_FACE）か本人の語が1つだけのとき（りょうり → 料理）。
        2つ以上（こうえん → 公園・講演・公演）や、ほかの表記もある程度使われる語（はし → 橋・箸）は決まらないのでかなのまま。
    並びの中に置けない名詞があれば、その並びは置かない。（2026-10-31）"""
    try:
        import ime_reconvert
        from morphology import tokenize
    except Exception:
        return []
    out = []
    n = 0

    def fits(first, last):
        # 名詞の後ろに来られるのは助詞か断定（だ・です）。を の直後で後ろに助詞の無い名詞（お時間をいただき、）は
        # 述語の形（動詞の連用形）を名詞と見たもの。名詞の後ろに な（ごめな）も名詞ではない
        nxt = spans[last + 1] if last + 1 < len(spans) else None
        prev = spans[first - 1][2] if first > 0 else before
        # 名詞＋する・いたす（お願いいたします・連絡します）も名詞の後ろの形
        suru = nxt is not None and nxt[4] == '動詞' and nxt[3][:1] in 'しすさせ' or (nxt is not None and nxt[3].startswith('いた'))
        # 漢字で書く名詞が続く（しょくじ｜けん）も複合語の切れ目。後ろの名詞もこの並びで置けなければ並びごと置かない
        # （2026-11-05 挙動関連担当の PC の測り: 名詞＋名詞の行が漢字にならない）。CN_LATTICE_NOUN_NOUN=0
        noun_next = (nxt is not None and nxt[4] == '名詞' and any(_kanji(c) for c in nxt[2])
                     and len(nxt[3]) >= MIN_WORD and os.environ.get('CN_LATTICE_NOUN_NOUN') != '0')
        if nxt is not None and not (nxt[4] == '助詞' or (nxt[4] == '助動詞' and nxt[2] in _COPULA) or suru or noun_next):
            return False
        if prev == 'を' and (nxt is None or nxt[4] != '助詞') and not noun_next:
            return False
        return True

    while n < len(spans):
        s, e, face, rd, pos = spans[n]
        # 1字の読みを含む名詞の並び（ご｜ぜん｜ちゅう: 格子が 5・膳・中 と切る）も、つないだ3字以上の読みが辞書の1語で、
        # 門を通る漢字だけの表記が1つ（午前中）ならそれ。CN_LATTICE_JOIN_SHORT=0
        if pos == '名詞' and os.environ.get('CN_LATTICE_JOIN_SHORT') != '0' and (len(rd) < MIN_WORD or (
                n + 1 < len(spans) and len(spans[n + 1][3]) < MIN_WORD)):
            js = None
            m = n + 1
            while m < len(spans) and m < n + 4 and spans[m][4] == '名詞' and spans[m][2] != spans[m][3]:
                m += 1
                rdj = ''.join(x[3] for x in spans[n:m])
                if len(rdj) < 3:
                    continue
                fj, _own = _everyday_faces(rdj, store, dict_index, LK)
                fj = [f for f in fj if all(_kanji(c) for c in f)]
                if len(fj) == 1:
                    js = (m, fj[0])
            if js is not None and fits(n, js[0] - 1):
                out.append((a + s, a + spans[js[0] - 1][1], js[1]))
                n = js[0]
                continue
        # 格子が漢字の接頭詞（好・御）で切った並びの後ろに名詞（こう｜えんか｜いじょう）は、接頭詞がかなのまま残る置き方
        # （こう宴会場）になる。区切りが怪しいので置かず紫。CN_LATTICE_PREFIX_PURPLE=0
        if (pos == '接頭詞' and any(_kanji(c) for c in face) and n + 1 < len(spans) and spans[n + 1][4] == '名詞'
                and os.environ.get('CN_LATTICE_PREFIX_PURPLE') != '0'):
            # 接頭詞の読みが お（お辞儀・お知らせ）なら、お＋語は和語の書き方でかなのままでよい（うに 11-01 和語はかなの
            # まま）。区切りの怪しさの紫は付けない（おじぎした が紫になっていた・2026-11-09）。CN_LATTICE_PREFIX_O=0 で前のまま
            if doubts is not None and not (rd == 'お' and os.environ.get('CN_LATTICE_PREFIX_O') != '0'):
                m_ = n + 1
                while m_ < len(spans) and spans[m_][4] == '名詞':
                    m_ += 1
                doubts.append((a + s, a + spans[m_ - 1][1]))
            return []
        if pos != '名詞' or not any(_kanji(c) for c in face):
            if pos == '名詞' and len(rd) >= MIN_WORD and not _kana_noun_ok(
                    rd, spans[n - 1][3] if n > 0 else '', spans[n + 1][3] if n + 1 < len(spans) else ''):
                return []
            n += 1
            continue
        # 続く名詞とつなぐと辞書の1語（行番号・電話番号）
        joined = None
        m = n + 1
        # 1字の読み（ご｜め → 米）はつながない。どの部分も2字以上の読み
        while m < len(spans) and m < n + 3 and spans[m][4] == '名詞' and any(_kanji(c) for c in spans[m][2]) \
                and len(spans[m][3]) >= MIN_WORD and len(rd) >= MIN_WORD:
            m += 1
            rdj = ''.join(x[3] for x in spans[n:m])
            fj, _own = _everyday_faces(rdj, store, dict_index, LK)
            fj = [f for f in fj if all(_kanji(c) for c in f)]
            if len(fj) == 1:
                joined = (m, fj[0])
        if joined is not None:
            m, f = joined
            if not fits(n, m - 1):
                return []
            out.append((a + s, a + spans[m - 1][1], f))
            n = m
            continue
        if len(rd) < MIN_WORD:
            return []
        if os.environ.get('CN_LATTICE_WAGO_SKIP') != '0' and n + 1 < len(spans) \
                and spans[n + 1][4] == '名詞' and any(_kanji(c) for c in spans[n + 1][2]) and _wago_noun(face, rd):
            # 和語の名詞（ひきつぎ）はかなのまま（うに 11-01 かなのままでよいのは和語）。並び全体を諦めず、
            # 続く漢語の名詞（しりょう）は置く（2026-11-04 うにの未解決タブ・作った例）
            n += 1
            continue
        # 名詞のすぐ後ろに名詞（がくせい｜けん）で、つないだ読みは辞書の1語でなく、後ろの語の表記が1つに決まらない
        # （券・権・件・県）なら、書くつもりの語が決まらない。かなのままにせず紫（決めるか紫・うに 10-18）
        # 前の名詞は表記が1つに決まり、後ろの名詞も2字以上の読みのときだけ（1字の読みの名詞が続く切り方
        # どうし｜た・おく｜と は、格子が用言の かな を名詞に切った形で、名詞の組ではない）
        if doubts is not None and n + 1 < len(spans) and spans[n + 1][4] == '名詞' \
                and any(_kanji(c) for c in spans[n + 1][2]) and len(spans[n + 1][3]) >= MIN_WORD:
            pf, pown = _everyday_faces(rd, store, dict_index, LK)
            pusual = [f for f in pf if f in pown or ime_reconvert._rank(f) <= COMMON_FACE]
            pother = [f for f in pf if f not in pusual and ime_reconvert._rank(f) <= OTHER_FACE]
            nf, nown = _everyday_faces(spans[n + 1][3], store, dict_index, LK)
            nusual = [f for f in nf if f in nown or ime_reconvert._rank(f) <= OTHER_FACE]
            if os.environ.get('CN_LATTICE_NO_TIME_TAIL') != '0' and len(rd) >= MIN_WORD:
                # 名詞のすぐ後ろ（複合語の後ろの要素）に時を表す名詞（昨日・明日）は来ない（ほんやく｜きのう → 機能）
                nusual = [f for f in nusual if not _time_noun(f)] or nusual
            if len(pusual) == 1 and not pother and len(nusual) >= 2:
                doubts.append((a + s, a + spans[n + 1][1]))
                return []
        toks = list(tokenize(rd))
        # かなで書くのが普通の語（副詞・副詞にもなる名詞・形容動詞の語幹: だいたい・いちばん・きれい）もかなのまま
        def _kana_kind(t):
            return t.pos == '副詞' or any(k in (t.pos_sub or '') for k in
                                         ('非自立', '代名詞', '数', '副詞可能', '形容動詞語幹'))
        after_noun = (n > 0 and spans[n - 1][4] == '名詞' and any(_kanji(c) for c in spans[n - 1][2])
                      and len(spans[n - 1][3]) >= MIN_WORD and os.environ.get('CN_LATTICE_NO_TIME_TAIL') != '0')
        # 格子が名詞と読み、すぐ後ろが を・が（副詞は を・が を取らない: いと｜を）なら、1語だけの解析の副詞（いと: 古語の
        # 副詞）は当てにしない。表記は、後ろの述語と組む例が Tatoeba（名詞＋格＋述語の組）に在る表記が1つのときだけ
        # （いと｜を｜察し → を・意図・察す）。漢語ならその表記、和語ならかなのまま。例が無ければ前のまま（副詞としてかな）。
        # CN_LATTICE_ADV_CASE=0 で前のまま（2026-11-08 手分けA）
        if (len(toks) == 1 and toks[0].pos == '副詞' and pos == '名詞' and n + 2 < len(spans)
                and spans[n + 1][4] == '助詞' and spans[n + 1][3] in ('を', 'が')
                and spans[n + 2][4] in ('動詞', '形容詞') and os.environ.get('CN_LATTICE_ADV_CASE') != '0'):
            pick = _case_pair_face(rd, spans[n + 1][3], spans[n + 2][2], store, dict_index, LK)
            if pick is not None:
                try:
                    import kana_keep as _kk
                    if _kk.is_kango(pick, rd) and fits(n, n):
                        out.append((a + s, a + e, pick))
                except Exception:
                    pass
                n += 1
                continue
        if len(toks) == 1 and _kana_kind(toks[0]) and not (
                after_noun and toks[0].pos_sub == '副詞可能' and pos == '名詞' and not _time_noun(face)):
            n += 1
            continue
        faces, own = _everyday_faces(rd, store, dict_index, LK)
        usual = [f for f in faces if f in own or ime_reconvert._rank(f) <= COMMON_FACE]
        # ほかの表記も一般に使われる語（はし → 橋・箸・端）は決まらない
        others = [f for f in faces if f not in usual and ime_reconvert._rank(f) <= OTHER_FACE]
        # 漢字で書く名詞のすぐ後ろ（複合語の後ろの要素）なら、時を表す名詞（昨日・明日）は候補にしない（翻訳｜機能）。
        # CN_LATTICE_NO_TIME_TAIL=0 で前のまま
        if after_noun:
            kept = [f for f in usual + others if not _time_noun(f)]
            if kept and len(kept) < len(usual + others):
                usual = [f for f in usual if f in kept] or [kept[0]]
                others = [f for f in others if f in kept and f not in usual]
        # 門を通る表記がその読みで1つだけの漢語（れんきゅう → 連休: 身近さの表で身近）は、一般の文章の順位が COMMON_FACE
        # より少し後ろでも表記は迷わない。決まらない紫にせず置く。CN_LATTICE_ONE_FAMILIAR=0
        if not usual and len(faces) == 1 and others == faces and os.environ.get('CN_LATTICE_ONE_FAMILIAR') != '0':
            try:
                import kana_keep as _kk
                # 門の外のほかの表記（でんき → 電気: 門を通らない）が一般によく使われるなら決めない（伝記 にしない）
                raw_ = LK._kanji_choices(rd, store, dict_index) or []
                if _kk.is_kango(faces[0], rd) and len(faces[0]) >= 2 \
                        and not any(f != faces[0] and ime_reconvert._rank(f) <= OTHER_FACE for f in raw_):
                    usual, others = list(faces), []
            except Exception:
                pass
        if len(usual) > 1 and not others and os.environ.get('CN_LATTICE_OWN_RARE') != '0':
            # 本人の語で珍しい表記（順位が OTHER_FACE より後ろ）が並んだだけなら、一般に身近な表記が1つなら決める
            # （使うほど直らなくなる形にしない・2026-11-05 挙動関連担当の PC の測り: 411 と 717 の2つで止まっていた）
            common = [f for f in usual if ime_reconvert._rank(f) <= COMMON_FACE]
            if len(common) == 1 and all(f in common or ime_reconvert._rank(f) > OTHER_FACE for f in usual):
                usual = common
        # 迷う表記がどれも和語（はし → 橋・箸・端、すき → 好き・隙）なら、どれに決まってもかなのまま（和語はかなのまま・
        # うに 11-01）。迷いの紫を付けない。CN_LATTICE_AMBIG_WAGO=0
        if (len(usual) > 1 or others) and os.environ.get('CN_LATTICE_AMBIG_WAGO') != '0':
            try:
                import kana_keep as _kk
                if all(not _kk.is_kango(f, rd) for f in usual + others):
                    n += 1
                    continue
            except Exception:
                pass
        if (len(usual) > 1 or others) and doubts is not None and fits(n, n) \
                and os.environ.get('CN_LATTICE_AMBIG_PURPLE') != '0':
            # 表記が決まらない名詞（こうえん → 公園・講演）は、かなのまま黙らず紫（決めるか紫・うに 10-18）。
            # ほかの名詞は置く（2026-11-05 挙動関連担当の PC の測り: 2語目が決まらず行ごと止まる）。CN_LATTICE_AMBIG_PURPLE=0
            doubts.append((a + s, a + e))
            n += 1
            continue
        if len(usual) != 1 or others or not fits(n, n):
            return []
        out.append((a + s, a + e, usual[0]))
        n += 1
    return out


def _case_pair_face(rd, case, pred_face, store, dict_index, LK):
    """読み rd の名詞の表記のうち、格 case と述語 pred_face（の言い切りの形）と組む例が Tatoeba の組の表に在るものが
    1つだけならそれ。無いか2つ以上なら None。"""
    try:
        import gzip
        import json
        from functools import lru_cache
        from morphology import tokenize
    except Exception:
        return None
    bases = set()
    for probe in (pred_face, pred_face + 'て'):
        toks = [t for t in tokenize(probe) if t.pos in ('動詞', '形容詞')]
        if toks and toks[0].start == 0:
            bases.add(getattr(toks[0], 'base_form', '') or toks[0].surface)
    if not bases:
        return None
    faces, _own = _everyday_faces(rd, store, dict_index, LK)
    hit = [f for f in faces if any(_tatoeba_pair(case, f, b) for b in bases)]
    return hit[0] if len(hit) == 1 else None


_PAIRS = None


def _tatoeba_pair(case, noun, pred):
    global _PAIRS
    if _PAIRS is None:
        _PAIRS = {}
        here = os.path.dirname(os.path.abspath(__file__))
        for fn in ('tatoeba_pairs.json.gz', 'tatoeba_case.json.gz'):
            try:
                import gzip
                import json
                with gzip.open(os.path.join(here, fn), 'rt', encoding='utf-8') as f:
                    _PAIRS.update(json.load(f).get('pairs') or {})
            except Exception:
                pass
    return _PAIRS.get(f'{case}\t{noun}\t{pred}', 0) > 0


def _inflected_here(s, e, toks):
    """[s, e) が、行の解析で ちょうど 用言＋助動詞（し｜ない・いたく｜ない）に切れているか。かなの文法の説明が用言と
    助動詞の並びで、格子だけが同じ読みの名詞（しない → 市内）に組んだ所は、書くつもりの用言のかな（2026-11-02 うに
    「しないデータ」が名詞に替わった）。名詞を置かない。"""
    inside = [t for t in toks if s <= t.start and t.end <= e]
    if not inside or inside[0].start != s or inside[-1].end != e:
        return False
    if any(t.start < s < t.end or t.start < e < t.end for t in toks):
        return False
    # 後ろがすぐ格助詞の を・が（しゃし｜ん｜を）なら、用言の言い切りではない（用言は の なしに を・が を取らない）。
    # 行の解析がかなの名詞を用言に切り損ねた形。CN_LATTICE_INFL_CASE=0
    if __import__('os').environ.get('CN_LATTICE_INFL_CASE') != '0' \
            and any(t.start == e and t.pos == '助詞' and t.surface in ('を', 'が') and '格助詞' in (t.pos_sub or '')
                    for t in toks):
        return False
    # 用言の後に助詞が続く所（ない｜か の ないか → 内科）も同じ（2026-11-02 うに「問題がないか」）
    if len(inside) >= 2 and inside[0].pos in ('動詞', '形容詞') and all(t.pos in ('助動詞', '助詞') for t in inside[1:]):
        return True
    # 用言の後ろの説明の ん・の（いい｜ん｜だ・行く｜ん｜です）も、用言の続き（2026-11-03 うに 未解決タブ: 言い切りの
    # 用言＋んだ を同じ読みの名詞にした）
    if len(inside) >= 2 and inside[0].pos in ('動詞', '形容詞') and inside[-1].surface in ('ん', 'の') \
            and all(t.pos in ('助動詞', '助詞') for t in inside[1:-1]) \
            and __import__('os').environ.get('CN_LATTICE_NODA') != '0':
        return True
    # て・で の直後の補助動詞（付いて｜しまい・書いて｜おく・見て｜いる）は用言の続き。同じ読みの名詞（姉妹）を置かない
    # （2026-11-07 うにの未解決タブ）。CN_LATTICE_TE_AUX=0 で前のまま
    if (__import__('os').environ.get('CN_LATTICE_TE_AUX') != '0' and inside[0].pos == '動詞'
            and (inside[0].pos_sub or '').startswith('非自立')
            and all(t.pos in ('助動詞', '助詞') for t in inside[1:])
            and any(t.end == s and t.surface in ('て', 'で') and '接続助詞' in (t.pos_sub or '') for t in toks)):
        return True
    # 助詞・助動詞だけに切れる所（ない｜か｜と の かと）を、格子が同じ読みの名詞（過渡）に組んだ形も書くつもりのかな
    return all(t.pos in ('助詞', '助動詞') for t in inside)


_CASE_HEADS = frozenset(('は', 'が', 'を', 'に', 'で', 'と', 'も', 'の', 'へ', 'から', 'まで', 'より'))


def propose(text, store, dict_index, surrounding=(), _skip=()):
    """[(start, end, 置く表記)] と 紫 [(start, end)]。置く表記は今までの置き方の候補の先頭。"""
    try:
        import reading_lattice as lat
        import last_keystroke as LK
    except Exception:
        return [], []
    places, doubts = [], []
    try:
        import pos_grammar
    except Exception:
        return [], []
    # 置くのは、文節の頭から始まるかなの並びだけ（行頭・記号の後・助詞の後）。漢字の語の尻尾に続くかな
    # （思ったより の たより・誤りがないか の がないか・食べてください の ください）は語の続きなので触らない
    try:
        import morphology
        toks_all = list(morphology.tokenize(text))
        starts = {0} | {t.end for t in toks_all if t.pos in ('助詞', '記号')}
        # 漢字で書いた用言の言い切り・連体の形（新しい｜ぷろじぇくと）の後ろも文節の頭。CN_LATTICE_AFTER_PRED=0
        if os.environ.get('CN_LATTICE_AFTER_PRED') != '0':
            starts |= {t.end for t in toks_all if t.pos in ('形容詞', '動詞') and t.infl_form == '基本形'
                       and any(_kanji(c) for c in t.surface) and (t.pos_sub or '') == '自立'}
            # 断定の で（おちそう｜で｜しんぱい）の後ろも文節の頭
            starts |= {t.end for t in toks_all if t.pos == '助動詞' and t.surface == 'で'}
        # 片仮名の語のすぐ後ろのかな（デバッグ｜めにゅー）も文節の頭と見る（送り仮名ではない）。CN_LATTICE_AFTER_KATA=0
        if os.environ.get('CN_LATTICE_AFTER_KATA') != '0':
            _gram = {t.start for t in toks_all if t.pos in ('助詞', '助動詞')}
            for _a0, _b0 in kana_runs(text):
                if _a0 > 0 and text[_a0] != 'ー' and 'ァ' <= text[_a0 - 1] <= 'ヶ' and _a0 not in _gram:
                    try:
                        _r0 = lat.best(text[_a0:_b0])
                    except Exception:
                        _r0 = None
                    # 格子が助詞・助動詞から読む並び（アプリ｜は…）は頭にしない
                    if _r0 is not None and _r0.words and _r0.words[0][2] not in ('助詞', '助動詞'):
                        starts.add(_a0)
        # 漢字の語のすぐ後ろのかなの並びが、格子で助詞から読む形（週末｜は｜かぞく…）なら、その助詞の後ろも文節の頭
        # （行の解析がかなを はか｜ぞ｜く と切り損ねて、助詞の後ろが頭にならなかった）。CN_LATTICE_HEAD_PARTICLE=0
        if os.environ.get('CN_LATTICE_HEAD_PARTICLE') != '0':
            for _a0, _b0 in kana_runs(text):
                if _a0 > 0 and _kanji(text[_a0 - 1]) and _b0 - _a0 > MIN_WORD + 1:
                    try:
                        _r0 = lat.best(text[_a0:_b0])
                    except Exception:
                        _r0 = None
                    if _r0 is not None and _r0.words and _r0.words[0][2] == '助詞' \
                            and _r0.words[0][1] in _CASE_HEADS:
                        starts.add(_a0 + len(_r0.words[0][1]))
    except Exception:
        return [], []
    if _skip:
        starts -= set(_skip)
    chosen_p = {}
    for a0, b in kana_runs(text):
        # 並びの中の文節の頭（の｜ほせい の ほせい）から後ろを見る。左の頭から順に、説明の付かない最初の並び
        a, kana = None, None
        for p in sorted(x for x in starts if a0 <= x < b):
            if b - p < MIN_WORD + 1:
                break
            # かなの文法で説明の付く並び（よい・おいしい・している・いとこの）は書くつもりで書いたかな。触らない。
            # 説明の付かない並び（ほせい・じに）だけ、区切りを格子で決める
            try:
                explained = pos_grammar.explain_kana_run(text[p:b])
            except Exception:
                explained = True
            a, kana = p, text[p:b]
            chosen_p[(a0, b)] = p
            # 頭から説明の付く並び（は｜すいぞくかんに）は、かなで書くのが普通の語（助詞・形式名詞・用言）はかなのまま、
            # 漢字で書くのが普通の名詞だけを置く（うに 10-31「かなだけの行も、漢字にするべき部分は漢字に」）
            break
        if a is None:
            continue
        try:
            r = lat.best(kana)
        except Exception:
            continue
        if r is None or not r.words:
            continue
        # 文節の頭が助詞・助動詞から始まる切り方（た｜伏せ）は切り方そのものが成り立たない。置かない
        if r.words[0][2] in ('助詞', '助動詞'):
            continue
        at = 0
        spans = []
        for face, rd, pos, _ed in r.words:
            spans.append((at, at + len(rd), face, rd, pos))
            at += len(rd)
        if at != len(kana):
            continue
        run_places = []
        whole = True     # 格子が漢字と見た語を1つでも置けなければ、この並びは置かない（他｜伏せ の 伏せ だけ置く形を避ける）
        if explained:
            got = [x for x in _explained_nouns(a, spans, store, dict_index, LK, text[a - 1:a] if a else '', doubts)
                   if not _inflected_here(x[0], x[1], toks_all)]
            if not _IN_ALT and os.environ.get('CN_LATTICE_KEY_ALT') != '0':
                alt = _key_alt(text, a, b, kana, spans, sorted(got), store, dict_index, surrounding, _skip)
                if alt is not None:
                    places.append(alt)
                    continue
            places.extend(got)
            # 説明の付く並びでも、伸ばし・半濁音を含む身近な外来語の名詞（こーひー）は片仮名で置く。CN_LATTICE_KATA_ALONE=0
            if os.environ.get('CN_LATTICE_KATA_ALONE') != '0':
                def kata_ok(face, pos):
                    return bool(face) and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in face) and pos == '名詞'
                # 続いた片仮名の語（すまーと｜ふぉん）はまとめて見る。どれも身近な外来語で、どれかが伸ばし・半濁音を含み、
                # 後ろが助詞・助動詞・並びの終わりのときだけ置く（スマート だけ置いて ふぉん を残さない）
                n_ = 0
                while n_ < len(spans):
                    if not kata_ok(spans[n_][2], spans[n_][4]):
                        n_ += 1
                        continue
                    m_ = n_
                    while m_ < len(spans) and kata_ok(spans[m_][2], spans[m_][4]):
                        m_ += 1
                    chain = spans[n_:m_]
                    nxt = spans[m_] if m_ < len(spans) else None
                    x0, x1 = a + chain[0][0], a + chain[-1][1]
                    if (all(_kata_common(c[2]) for c in chain) and x1 - x0 >= 3
                            and any(c in 'ーぱぴぷぺぽ' for c in text[x0:x1])
                            and (nxt is None or nxt[4] in ('助詞', '助動詞'))
                            and not any(g[0] < x1 and x0 < g[1] for g in got)):
                        places.extend((a + c[0], a + c[1], c[2]) for c in chain)
                    n_ = m_
            continue
        kata = []
        for s, e, face, rd, pos in spans:
            if (os.environ.get('CN_LATTICE_KATAKANA') != '0' and face and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in face)
                    and pos == '名詞' and len(rd) >= MIN_WORD and _kata_common(face)):
                # 外来語の名詞（にゅうりょくみす の ミス）は片仮名で置く（うに 11-01「外来語は片仮名に」）。漢字の語と
                # 一緒に置くときだけ（片仮名の語だけの並びは、平仮名の語の読み違いのことがある: ねこ）
                kata.append((a + s, a + e, face))
                continue
            if not any(_kanji(c) for c in face):
                # かなのままの内容の語（すいぞ｜区間 の すいぞ）が残る切り方は、切り方そのものが怪しい。置かない
                # 名詞のすぐ後ろの する（せいり｜する: サ変の名詞＋する）は内容の語ではない。CN_LATTICE_SURU=0
                if pos == '動詞' and rd == 'する' and face == rd and s > 0 \
                        and os.environ.get('CN_LATTICE_SURU') != '0' \
                        and any(x[1] == s and x[4] == '名詞' for x in spans):
                    continue
                # 格子がかなの表記で読む用言（とっ｜た）は和語の用言でかなのまま。並びは諦めない（漢字の用言と同じ）。
                # 後ろが助詞・助動詞か並びの終わりのときだけ。CN_LATTICE_KANA_VERB=0
                if (pos in ('動詞', '形容詞') and os.environ.get('CN_LATTICE_KANA_VERB') != '0'
                        and all(x[4] in ('助詞', '助動詞') for x in spans if x[0] == e)):
                    continue
                if pos not in ('助詞', '助動詞') and len(rd) >= MIN_WORD:
                    whole = False
                    break
                continue
            # 1字の読みの用言（き｜た・み｜て）も、すぐ後ろが助動詞か て・で なら用言の形。CN_LATTICE_VERB_ONE=0
            if pos == '動詞' and len(rd) == 1 and os.environ.get('CN_LATTICE_VERB_ONE') != '0' \
                    and any(x[0] == e and (x[4] == '助動詞' or (x[4] == '助詞' and x[3] in ('て', 'で'))) for x in spans):
                continue
            if pos in ('動詞', '形容詞') and len(rd) >= MIN_WORD and os.environ.get('CN_LATTICE_VERB_KANA') != '0':
                # 用言（よむ・かい）はかなのまま（和語はかなのまま・うに 11-01）。並び全体は諦めず、続く名詞は置く
                # （2026-11-05 挙動関連担当の PC の測り: 用言＋名詞＋助詞＋用言 の行が漢字にならない）。CN_LATTICE_VERB_KANA=0
                continue
            if pos not in _CONTENT_POS or len(rd) < MIN_WORD:
                whole = False
                break
            # 表記は今までの置き方の候補（本人の語彙→辞書→身近さの門）。格子の表記はそのまま使わない
            try:
                faces = LK._kanji_choices(rd, store, dict_index)
            except Exception:
                faces = []
            # 身近さの門は今までの置き方と同じ（本人の語は置く・表に無い2字の漢語は置かない）
            own = _own_kept(rd, set(LK._own_faces(rd, store)))
            raw = faces
            faces = [f for f in faces if f in own or (not LK._not_everyday_kango(f) and LK._kango_reads_as(f, rd))]
            if not faces and raw and raw[0] == face and len(raw) == 1 and len(rd) >= 3 \
                    and os.environ.get('CN_LATTICE_RARE_SKIP') != '0':
                # 格子の語が辞書でもその読みの唯一の表記（ぎだい → 議題）で、身近さの門だけを通らない語は、その語だけかなのまま
                # にして、並びのほかの身近な語（明日・会議・整理）は置く（区切りは確か。1語のために行全体をかなのまま・紫に
                # しない）。CN_LATTICE_RARE_SKIP=0 で前のまま
                continue
            if not faces:
                # 格子が珍しい漢字の語（みす → 御簾）に読んだ所でも、読みの片仮名が身近な外来語（ミス）なら片仮名で置く
                # （漢字の語と一緒に置くときだけ・下の run_places）。2026-11-06 PC の測り: ローマ字の かなだけの行で
                # 入力ミスを… が漢字にならない。CN_LATTICE_KATA_FALLBACK=0 で前のまま
                if _kata_fallback(face, rd, a, s, e, kata):
                    continue
                whole = False
                break
            # 名詞には送り仮名の付く表記（ほん → 掘ん）を選ばない（2026-11-05 挙動関連担当の PC の測り）
            whole_kanji = [f for f in faces if all(_kanji(c) for c in f)]
            if whole_kanji and os.environ.get('CN_LATTICE_NOUN_FACE') != '0':
                faces = whole_kanji
            chosen = faces[0]
            # 名詞のすぐ後ろ（複合語の後ろの要素）に時を表す名詞（昨日・明日: 副詞にもなる名詞）は来ない。候補の先頭がそれで、
            # 格子の表記（機能）が候補の中にあり時の名詞でなければ、格子の表記にする（ほんやく｜きのう → 翻訳＋機能）。
            # CN_LATTICE_NO_TIME_TAIL=0 で前のまま
            if (chosen != face and face in faces and run_places and run_places[-1][1] == a + s
                    and os.environ.get('CN_LATTICE_NO_TIME_TAIL') != '0'
                    and _time_noun(chosen) and not _time_noun(face)):
                chosen = face
            # 格子の表記と候補の先頭の漢字が食い違うなら、区切りは同じでも語が決まらない＝置かない
            if {c for c in chosen if _kanji(c)} != {c for c in face if _kanji(c)}:
                # 漢字1字の語（かいぎ｜しつ の しつ: 候補の先頭は 悉）は1字では決まらない。すぐ前に置く名詞と
                # つないだ読みが辞書の1語（会議室）になり、格子の表記と同じなら、つないで置く。CN_LATTICE_JOIN_FIRST=0
                if (len(face) == 1 and _kanji(face) and run_places and run_places[-1][1] == a + s
                        and os.environ.get('CN_LATTICE_JOIN_FIRST') != '0'):
                    q = run_places[-1]
                    try:
                        j = LK._kanji_choices(text[q[0]:a + e], store, dict_index)
                    except Exception:
                        j = []
                    if j and j[0] == q[2] + face:
                        run_places[-1] = (q[0], a + e, j[0])
                        continue
                if _kata_fallback(face, rd, a, s, e, kata):
                    continue
                whole = False
                break
            run_places.append((a + s, a + e, chosen))
        # 名詞＋漢字1字の名詞（せいきゅう｜しょ → 請求＋署）は、つないだ読みが辞書の1語（請求書）ならそれにする
        # （1字の表記は 署・書・所 と決まらない）。CN_LATTICE_JOIN_ONE=0 で前のまま
        if whole and len(run_places) > 1 and os.environ.get('CN_LATTICE_JOIN_ONE') != '0':
            merged = [run_places[0]]
            for p in run_places[1:]:
                q = merged[-1]
                if q[1] == p[0] and len(p[2]) == 1 and all(_kanji(c) for c in q[2] + p[2]):
                    try:
                        j = LK._kanji_choices(text[q[0]:p[1]], store, dict_index)
                    except Exception:
                        j = []
                    if j and len(j[0]) == len(q[2]) + 1 and j[0].startswith(q[2]) and all(_kanji(c) for c in j[0]):
                        merged[-1] = (q[0], p[1], j[0])
                        continue
                merged.append(p)
            run_places = merged
            # つないでも辞書の1語にならない、名詞のすぐ後ろの漢字1字（見積もり｜署）は表記が決まらない（署・書・所）。
            # 並びは置かず紫にする。CN_LATTICE_LONE_ONE=0
            if os.environ.get('CN_LATTICE_LONE_ONE') != '0':
                lone = [p for k_, p in enumerate(run_places) if k_ > 0 and run_places[k_ - 1][1] == p[0]
                        and len(p[2]) == 1 and _kanji(p[2])]
                if lone:
                    whole = False
                    doubts.extend((p[0], p[1]) for p in lone)
        if whole and run_places and os.environ.get('CN_LATTICE_RUN_INFLECTED') != '0':
            # 行の解析が用言＋助詞と切る所（かい｜て｜から を 買い手 に）は、説明の付く並びと同じく置かない
            # （て・で で終わる所＝用言のて形だけ。ほかは行の解析がかなの行を切り損ねる: 先日・予算 を落としていた）
            run_places = [x for x in run_places if not (text[x[1] - 1] in 'てで' and _inflected_here(x[0], x[1], toks_all))]
        if whole and run_places and os.environ.get('CN_LATTICE_KEY_ALT') != '0':
            alt = None if _IN_ALT else _key_alt(text, a, b, kana, spans, run_places, store, dict_index,
                                                 surrounding, _skip)
            if alt is not None:
                places.append(alt)
                continue
        if whole and run_places:
            places.extend(run_places + kata)
        elif whole:
            # 漢字の語が無くても、伸ばし（めにゅー・こーひー）か半濁音（ぱそこん）を含む身近な外来語は片仮名で置く
            # （平仮名の語の読み違い ねこ→ネコ は伸ばしも半濁音も無い）。CN_LATTICE_KATA_ALONE=0 で前のまま
            if os.environ.get('CN_LATTICE_KATA_ALONE') != '0':
                kata = [x for x in kata if x[1] - x[0] >= 3
                        and any(c in 'ーぱぴぷぺぽ' for c in text[x[0]:x[1]])]
                places.extend(kata)
    # 並びの最初の文節の頭から何も置けず紫も無い並び（試験に｜おちそうで｜しんぱい: 格子が おちそうでしんぱい を
    # 読み損ねた）は、次の文節の頭から見直す（後ろの名詞 しんぱい を置く）。CN_LATTICE_NEXT_HEAD=0
    if os.environ.get('CN_LATTICE_NEXT_HEAD') != '0' and len(_skip) < 3:
        # 置いた所・紫の所の後ろに、まだ見ていない文節の頭があれば、そこから後ろを見直す（試験｜に｜おちそうで｜しんぱい）
        retry, skip = [], set(_skip)
        for (a0, b), p in chosen_p.items():
            got_ = [x[1] for x in places + doubts if a0 <= x[0] < b]
            last = max(got_) if got_ else p + 1
            q = min((q for q in starts if q >= last and q > p and b - q >= MIN_WORD + 1), default=None)
            if q is None:
                continue
            retry.append((q, b))
            skip |= {x for x in starts if a0 <= x < q}
        if retry:
            try:
                sp, sd = propose(text, store, dict_index, surrounding, tuple(sorted(skip)))
            except Exception:
                sp, sd = [], []
            places.extend(x for x in sp if any(q <= x[0] and x[1] <= b for q, b in retry))
            doubts.extend(x for x in sd if any(q <= x[0] and x[1] <= b for q, b in retry))
    if doubts and os.environ.get('CN_LATTICE_AMBIG_PURPLE') != '0':
        # 行の解析が用言と読む所（書いて｜あん｜の の あん: ある の縮まった形）は、格子の名詞の迷いではない
        doubts = [d for d in doubts
                  if not any(t.start == d[0] and t.pos in ('動詞', '形容詞', '助動詞', '助詞') for t in toks_all)]
        # 用言の語の中に収まる所（読んでてく**ださい**: ください の中の さい）も、名詞の迷いではない。CN_LATTICE_INSIDE_VERB=0
        if os.environ.get('CN_LATTICE_INSIDE_VERB') != '0':
            doubts = [d for d in doubts
                      if not any(t.start <= d[0] and d[1] <= t.end and len(t.surface) > d[1] - d[0]
                                 and (t.pos in ('動詞', '形容詞', '助動詞')
                                      # 漢字を含む語の中のかな（**やり**方・**お**昼）も、名詞の迷いではない
                                      or any('一' <= c <= '鿿' for c in t.surface))
                                 for t in toks_all)]
        # 行の解析で、迷いの所に掛かる語がどれも名詞でない（副詞・用言・機能語・形式名詞: どうにか・こと｜ない・
        # でかく｜なり）なら、格子が接頭詞や名詞に切った読みの迷いで、書いた語の迷いではない（2026-11-08 補正担当の
        # 正しい文の試し）。CN_LATTICE_NOUNLESS=0 で前のまま
        if os.environ.get('CN_LATTICE_NOUNLESS') != '0':
            def _nounless(d):
                over = [t for t in toks_all if t.start < d[1] and d[0] < t.end]
                if not over:
                    return False
                for t in over:
                    if t.pos == '名詞' and not (t.pos_sub or '').startswith('非自立'):
                        return False
                    if t.pos in ('接頭詞', '記号', 'フィラー', '感動詞'):
                        return False
                return any(t.pos in ('副詞', '形容詞', '動詞') and len(t.surface) >= 2 for t in over)
            doubts = [d for d in doubts if not _nounless(d)]
        # 行の解析がちょうどその所を形式名詞（名詞・非自立: ふり・ところ・ため）と読むなら、かなで書くのが普通の語で、
        # 表記の迷いではない（金持ちのふりをする が紫になっていた・2026-11-09）。CN_LATTICE_FORMAL_NOUN=0 で前のまま
        if os.environ.get('CN_LATTICE_FORMAL_NOUN') != '0':
            doubts = [d for d in doubts
                      if not any(t.start == d[0] and t.end == d[1] and t.pos == '名詞'
                                 and (t.pos_sub or '').startswith('非自立') for t in toks_all)]
            # 行の解析で、迷いの所に掛かる語がどれも 形式名詞・接尾（さん・こと）か 助詞・助動詞 なら、格子が機能語の並び
            # を別の名詞（こと｜しか → 今年・さん → 三）と読んだ迷いで、書いた語の迷いではない（ジャクソンさん の さん・
            # のことしか が紫になっていた・2026-11-09）。CN_LATTICE_FUNC_ONLY=0 で前のまま
            if os.environ.get('CN_LATTICE_FUNC_ONLY') != '0':
                def _func_only(d):
                    over = [t for t in toks_all if t.start < d[1] and d[0] < t.end]
                    return bool(over) and all(
                        t.pos in ('助詞', '助動詞') or (t.pos == '名詞' and (t.pos_sub or '').startswith(('非自立', '接尾')))
                        for t in over)
                doubts = [d for d in doubts if not _func_only(d)]
    return places, doubts


KEY_ALT_MARGIN = int(os.environ.get('CN_LATTICE_KEY_ALT_MARGIN', '1000'))
_IN_ALT = False
_ALT_BAD_POS = ('未知', 'フィラー', '感動詞', '副詞', '接頭詞', '記号')


def _key_alt(text, a, b, kana, spans, run_places, store, dict_index, surrounding, _skip):
    """名詞だけの並び（やがい｜ぶんしょう → 野外＋文章）で、続いた名詞の組が辞書の1語でも身近な語でもないとき、並び全体を
    1打違い（隣のキー）に打ち直した読みを同じ置き方で置いてみる。置いた形が名詞で終わる句（形容詞・連体の形＋名詞:
    ながい文章）になり、行の自然さ（morphology.path_cost）が元の置き方より KEY_ALT_MARGIN 以上よく、二番とも離れて
    いれば、そちらで置く（うに 11-08「初期状態で補正できないなら直すべき」・本人の語彙に頼らない）。
    戻り値 (a, b, 置く表記) か None。CN_LATTICE_KEY_ALT=0 で見ない。"""
    if len(run_places) < 2 or any(x[4] != '名詞' for x in spans):
        return None
    if run_places[0][0] != a or run_places[-1][1] != b \
            or any(q[1] != p[0] for q, p in zip(run_places, run_places[1:])):
        return None
    try:
        import learned_gate
        import morphology
        from contextual_repair import key_repairs
    except Exception:
        return None
    if any(learned_gate._known_compound(q[2] + p[2]) for q, p in zip(run_places, run_places[1:])):
        return None
    here = ''.join(x[2] for x in run_places)
    try:
        base = morphology.path_cost(text[:a] + here + text[b:])
    except Exception:
        base = None
    if base is None:
        return None
    got = []
    for row in key_repairs(kana, text[a - 1:a] if a else '', text[b:b + 1]):
        rd = getattr(row, 'reading', row)
        if rd == kana or len(rd) != len(kana) or getattr(row, 'operation', '') != 'adjacent_substitution':
            continue
        alt_text = text[:a] + rd + text[b:]
        global _IN_ALT
        _IN_ALT = True
        try:
            sp, sd = propose(alt_text, store, dict_index, surrounding, _skip)
        except Exception:
            continue
        finally:
            _IN_ALT = False
        if any(a <= d[0] < b for d in sd):
            continue
        face = rd
        for s0, e0, f0 in sorted((x for x in sp if a <= x[0] and x[1] <= b), reverse=True):
            face = face[:s0 - a] + f0 + face[e0 - a:]
        faces_ = [face] if any(_kanji(c) for c in face) else []
        # 打ち直しが1つの名詞の中だけなら、ほかの名詞は元の置き方のまま、その名詞の所だけ打ち直した読み（かな）にした形も
        # 見る（やがい｜文章 → ながい｜文章: 打ち直した並びを置き直すと、語彙によっては 文章 が決まらない）
        diff = [k for k in range(len(rd)) if rd[k] != kana[k]]
        inside = [q for q in run_places if diff and q[0] - a <= diff[0] and diff[-1] < q[1] - a]
        if len(inside) == 1:
            q = inside[0]
            f2 = ''.join(rd[x[0] - a:x[1] - a] if x is q else x[2] for x in run_places)
            if f2 not in faces_ and any(_kanji(c) for c in f2):
                faces_.append(f2)
        for face in faces_:
            line2 = text[:a] + face + text[b:]
            try:
                toks = [t for t in morphology.tokenize(line2) if a <= t.start and t.end <= a + len(face)]
                cost = morphology.path_cost(line2)
            except Exception:
                continue
            if cost is None or not toks or toks[-1].pos != '名詞' or toks[0].pos in ('助詞', '助動詞'):
                continue
            if any(t.pos in _ALT_BAD_POS or (t.pos == '名詞' and len(t.surface) == 1 and not _kanji(t.surface))
                   for t in toks):
                continue
            got.append((cost, face))
    if not got:
        return None
    got.sort()
    if got[0][0] > base - KEY_ALT_MARGIN:
        return None
    if len(got) > 1 and got[1][0] - got[0][0] < KEY_ALT_MARGIN:
        return None
    return (a, b, got[0][1])


def _time_noun(face):
    """時を表す名詞（昨日・明日・先週: 解析の細分類が 副詞可能 の1語）か。"""
    try:
        import morphology
        toks = list(morphology.tokenize(face))
    except Exception:
        return False
    return len(toks) == 1 and toks[0].pos == '名詞' and toks[0].pos_sub == '副詞可能'


def _joined_word_ok(face, done, at, store, dict_index):
    """置く名詞 face と done[at:] に続く漢字の語をつないだ形が、辞書の語（またはその頭）か。"""
    try:
        import morphology
        import last_keystroke as LK
        from ime_reconvert import _freq
        toks = [t for t in morphology.tokenize(done[at:]) if t.start == 0]
        if not toks:
            return True
        t = toks[0]
        run = t.surface
        if not run or not all(_kanji(c) for c in run):
            return True
        rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (t.reading if t.has_reading else ''))
        wf = _freq() or {}
        joined = face + run
        if joined in wf:
            return True
        # 2字以上の漢字の語が続く（会議＋室 でなく 会議＋資料）ときは、別の語の並びとして普通
        if len(run) >= 2:
            return True
        frd = None
        return any(f == joined for f in (LK._kanji_choices(_reading_of(face) + rd, store, dict_index) or [])[:8])
    except Exception:
        return True


def _reading_of(face):
    try:
        import morphology
        return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
                       for t in morphology.tokenize(face) for c in (t.reading if t.has_reading else t.surface))
    except Exception:
        return ''


def _kata_fallback(face, rd, a, s, e, kata):
    """格子が珍しい漢字の語（みす → 御簾）に読んだ名詞でも、読みの片仮名が身近な外来語（ミス）なら片仮名で置く。
    格子の表記がよく使う字（ばん → 版）なら外来語にしない。2026-11-06 PC の測り: ローマ字のかなだけの行で
    入力ミスを… が漢字にならない。CN_LATTICE_KATA_FALLBACK=0 で前のまま"""
    if os.environ.get('CN_LATTICE_KATA_FALLBACK') == '0' or len(rd) < MIN_WORD:
        return False
    try:
        import ime_reconvert
        if not any(_kanji(c) for c in face) or ime_reconvert._rank(face) <= OTHER_FACE:
            return False
    except Exception:
        return False
    kf = ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in rd)
    if not _kata_common(kf):
        return False
    kata.append((a + s, a + e, kf))
    return True


def _wago_noun(face, rd):
    try:
        import kana_keep
        return not kana_keep.is_kango(face, rd)
    except Exception:
        return False


def _kata_common(face):
    try:
        import ime_reconvert as R
        rk = R._rank(face)
    except Exception:
        return False
    return 0 < rk <= KATA_COMMON


def _doubt_marks(line, result, done, doubts):
    """置けなかったかなの名詞の組（表記が決まらない）に紫。ほかの補正が触った所・紫の所には付けない。"""
    if not doubts or done != line:
        return result
    out = dict(result)
    out['odd_spans'] = list(result.get('odd_spans') or []) + [(x, y) for x, y in doubts]
    # 読みは合っていて表記だけ決まらない紫。打ち違いの戻し（odd_respell）は当てない（読みの1打を替えた別の語にしない）
    out['face_doubt_spans'] = [(x, y) for x, y in doubts]
    return out


PURPLE_PLACE_GAIN = 3000   # 紫の上に置くのは、行の並びの費用がこれだけ下がるとき


def _place_over_purple(line, result, store, dict_index):
    """かなの並び全体が「品詞として識別できない」紫（にゅうりょくみすがおおい: 入力＋ミス の語の並び）でも、格子が
    並びを語にぴったり切れて置ける語があり、置くと行の費用がはっきり下がるなら置いて、その紫を外す（2026-11-06
    うにの画面: かなだけの行の外来語の混ざった名詞が漢字・片仮名にならない）。前の段が直した行には触らない。
    CN_LATTICE_OVER_PURPLE=0 で前のまま"""
    if os.environ.get('CN_LATTICE_OVER_PURPLE') == '0':
        return result
    done = result.get('corrected') or line
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    changed = []
    if done != line:
        # 前の段が行の別の所を直した行（来月から新しい｜ぷろじぇくと…）でも、紫がどれも直していない所にあれば、直した行の上で
        # 同じく置く（直した所には重ねない）。CN_LATTICE_OVER_PURPLE_FIXED=0 で前のまま（直した行には触らない）
        if os.environ.get('CN_LATTICE_OVER_PURPLE_FIXED') == '0':
            return result
        ops0 = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
        changed = [(j1, j2) for tag, i1, i2, j1, j2 in ops0 if tag != 'equal']
        moved = []
        for a, b in odd:
            m = [(a - i1 + j1, b - i1 + j1) for tag, i1, i2, j1, j2 in ops0 if tag == 'equal' and i1 <= a and b <= i2]
            if not m:
                return result
            moved.append(m[0])
        odd = moved
    try:
        places, _doubts = propose(done, store, dict_index)
    except Exception:
        return result
    places = [p for p in places if not any(x <= p[1] and p[0] <= y for x, y in changed)]
    if not places:
        return result
    # 紫がどれも、置く語の並びの所（かなだけ）にあること
    lo, hi = min(p[0] for p in places), max(p[1] for p in places)
    if not all(all(_hira(c) for c in done[a:b]) for a, b in odd):
        return result
    # 置く語の外のかなの紫（えきの｜ちかくです: 行の解析が ちかく を形容詞に読んで です と合わないとした紫）も、
    # 置いたあとに残るかながどれも文法で説明できるときだけ外す（費用の差では外さない）。CN_LATTICE_OVER_PURPLE_OUT=0
    outside = not all(a <= hi and lo < b for a, b in odd)
    if outside and os.environ.get('CN_LATTICE_OVER_PURPLE_OUT') == '0':
        return result
    import morphology
    base = morphology.path_cost(done)
    new = done
    for s, e, face in sorted(places, reverse=True):
        new = new[:s] + face + new[e:]
    cost = morphology.path_cost(new)
    if base is None or cost is None:
        return result
    if outside or base - cost < PURPLE_PLACE_GAIN:
        # 費用で決まらなくても、置いたあとに残るかなの並びがどれも、かなの文法で説明できるなら置く
        # （入力ミス｜がおおくてこまる）。説明の付かない並びが残るなら打ち違いかもしれないので置かない
        try:
            import re
            import pos_grammar
            runs = [(m.start(), m.end()) for m in re.finditer('[ぁ-ゖー]+', new)]
            if not runs or not all(pos_grammar.explain_kana_run(new[a:b], after_kanji=a > 0 and not _hira(new[a - 1]))
                                   for a, b in runs):
                return result
        except Exception:
            return result
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + [[done[s:e], f, '読みの区切り'] for s, e, f in places],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops],
                'unsure_spans': [], 'odd_spans': [], 'odd_reasons': []})
    if outside:
        # 外した紫の所（置いた後の行の位置）。後ろの段が直した行を解析し直して同じ所に紫を付け直さないよう渡す
        cleared = []
        for a, b in odd:
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, new, autojunk=False).get_opcodes():
                if tag == 'equal' and i1 <= a and b <= i2:
                    cleared.append((a - i1 + j1, b - i1 + j1))
        out['_purple_cleared'] = cleared
    return out

_I_ROW = 'きしちにひみりぎじぢびぴ'
_ROW_OF = {}
for _row in ('かきくけこ', 'さしすせそ', 'たちつてと', 'なにぬねの', 'はひふへほ', 'まみむめも', 'らりるれろ',
             'がぎぐげご', 'ざじずぜぞ', 'だぢづでど', 'ばびぶべぼ', 'ぱぴぷぺぽ'):
    for _c in _row:
        _ROW_OF[_c] = _row[1]


def _yoon_slip(line, result):
    """ゃゅょ の前がイ段でない（めなゅー: な＋ゅ は書けない）所は打ち違い。前の字を同じ行のイ段（に）か近いキーに替えて、
    かなの並びが身近な外来語（メニュー）になるものが1つだけなら片仮名にして直す。決まらなければ紫。
    ほかの補正が触った行・紫のある行には触らない（2026-11-06 うにの画面）。CN_LATTICE_YOON_SLIP=0 で前のまま"""
    if os.environ.get('CN_LATTICE_YOON_SLIP') == '0':
        return None
    done = result.get('corrected') or line
    if done != line or result.get('odd_spans'):
        return None
    try:
        from kana_layout import nearby_candidates
    except Exception:
        nearby_candidates = None
    for i, ch in enumerate(line):
        if ch not in 'ゃゅょ' or i == 0 or not _hira(line[i - 1]) or line[i - 1] in _I_ROW:
            continue
        k = i - 1
        a = k
        while a > 0 and (_hira(line[a - 1]) or line[a - 1] == 'ー'):
            a -= 1
        b = i + 1
        while b < len(line) and (_hira(line[b]) or line[b] == 'ー'):
            b += 1
        alts = set()
        if line[k] in _ROW_OF:
            alts.add(_ROW_OF[line[k]])
        if nearby_candidates is not None:
            try:
                alts |= {x for x, _d in nearby_candidates(line[k], max_dist=1.0, include_phonetic=False)
                         if x in _I_ROW}
            except Exception:
                pass
        hits = []
        for alt in sorted(alts):
            # 直した字から後ろへ、身近な片仮名の語になる一番長い並び（デバッグ｜めにゅー）
            for s0 in range(a, k + 1):
                for e0 in range(b, i, -1):
                    rd = line[s0:k] + alt + line[k + 1:e0]
                    face = ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in rd)
                    if len(face) >= 3 and _kata_common(face):
                        hits.append((s0, e0, face))
                        break
                else:
                    continue
                break
        if len(hits) == 1:
            s0, e0, face = hits[0]
            new = line[:s0] + face + line[e0:]
            out = dict(result)
            out.update({'original': line, 'corrected': new, 'changed': True,
                        'details': list(result.get('details') or []) + [[line[s0:e0], face, 'かな入力']],
                        'spans': [[s0, s0 + len(face)]], 'original_spans': [[s0, e0]], 'unsure_spans': []})
            return out
        out = dict(result)
        out['odd_spans'] = [(a, b)]
        out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, 'かなの小書き接続')]
        return out
    return None


ROLLIN_RUN = 24      # 1字抜きを試すかなの並びの長さの上限
ROLLIN_SHORT = 12    # これを超える並びでは、助詞・用言の字は抜かない
ROLLIN_READ = 3      # 抜いて置ける語の読みの長さの下限
ROLLIN_EXPLAINED_GAIN = 4000   # 説明の付く並びを紫にするのは、抜いて置いた行の費用がこれ以上下がるとき
ROLLIN_GAIN = 10000  # 抜いて置いた行の費用の下がりがこれ未満なら紫


def _rollin_delete(line, result, store, dict_index):
    """格子が何も置けないかなだけの行で、かな1字を抜くと抜いた所をまたいで漢字の名詞（身近な表記）が置ける
    （せつさ|めい → 説明: 巻き込みの余計な1字）なら、抜いて置く。抜く所の候補が2つ以上なら決めずに紫。
    前の段が触った行・紫のある行には触らない（2026-11-06 うにの画面: かなの巻き込みが紫も付かずに残る）。
    CN_LATTICE_ROLLIN=0 で前のまま"""
    if os.environ.get('CN_LATTICE_ROLLIN') == '0':
        return None
    done = result.get('corrected') or line
    if result.get('odd_spans'):
        return None
    if done != line:
        # 前の段がほかの所だけを直した行（せいきゅう → 請求）は、直した後の行で見る（直した所のかなの並びは見ない）。
        # CN_LATTICE_ROLLIN_AFTER=0 で前のまま
        if os.environ.get('CN_LATTICE_ROLLIN_AFTER') == '0':
            return None
        touched = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
                   if o[0] != 'equal']
        line = done
    else:
        touched = []
    # 浮いた濁点・半濁点の行は、その戻しの段（_lone_mark_fill ほか）に任せる。
    if '゛' in line or '゜' in line:
        return None
    # ローマ字の残った行（かいscあつ）は、英字の戻しの段に任せる
    if any(c.isascii() and c.isalpha() for c in line):
        return None
    # 書けない小書き（せいきく｜ゅう）の行は、その前の1字を抜く形だけ試す
    must = {q - 1 for q, c in enumerate(line)
            if c in 'ゃゅょ' and q and _hira(line[q - 1]) and line[q - 1] not in _I_ROW + 'ー'}
    import morphology
    found = []
    explained_runs = set()
    for a, b in kana_runs(line):
        if b - a > ROLLIN_RUN or b - a < ROLLIN_READ + 1:
            continue
        if any(x < b and a < y for x, y in touched):
            continue
        # 並びまるごとが活用の文法と機能語で説明の付く形（どのような: どの｜よう｜な）は抜かない（2026-11-07 例文 Tatoeba の
        # 正しい文で紫になり、後の段が どのように に替えていた）。CN_LATTICE_ROLLIN_EXPLAINED=0 で前のまま
        if os.environ.get('CN_LATTICE_ROLLIN_EXPLAINED') != '0':
            try:
                import pos_grammar
                if pos_grammar.explain_kana_run(line[a:b], before_kanji=b < len(line) and _kanji(line[b])):
                    # 説明の付く並びでも、1字抜くと漢字の名詞が置けて行の費用が大きく下がる形（でん｜なき｜だい →
                    # 電気代）は見る。紫にするだけ（決めない）。CN_LATTICE_ROLLIN_EXPLAINED_GAIN=0 で前のまま
                    if os.environ.get('CN_LATTICE_ROLLIN_EXPLAINED_GAIN') == '0':
                        continue
                    explained_runs.add((a, b))
            except Exception:
                pass
        # 抜く字が、元の並びの格子の切り方で長い語（拝見・下さい）や用言（いい）の中にあれば、その字は語の一部。抜かない
        # 並びの頭と、並びの中の助詞の後ろ（は｜ひがわり）から切った格子のどれかで語の中なら抜かない
        cover = {}
        try:
            import reading_lattice as lat
            heads = {a} | {a + t.end for t in morphology.tokenize(line[a:b]) if t.pos == '助詞' and t.end < b - a}
        except Exception:
            heads = {a}
        for h in sorted(heads):
            try:
                r0 = lat.best(line[h:b])
            except Exception:
                r0 = None
            if r0 is None or not r0.words:
                continue
            at = h
            for _f, rd, pos, _ed in r0.words:
                for q in range(at, at + len(rd)):
                    if q not in cover or len(rd) > cover[q][0]:
                        cover[q] = (len(rd), pos)
                at += len(rd)
        exp_func = set()
        if (a, b) in explained_runs:
            # 説明の付く並びでは、解析が助詞・助動詞や2字以上の名詞・動詞と読む字（ただい｜の｜かち の か）は抜かない
            try:
                exp_func = {a + q for t in morphology.tokenize(line[a:b])
                            if t.pos in ('助詞', '助動詞') or (t.pos in ('名詞', '動詞') and len(t.surface) >= 2)
                            for q in range(t.start, t.end)}
            except Exception:
                exp_func = set()
        for k in range(a, b):
            if line[k] in 'ー' or (must and k not in must) or k in exp_func:
                continue
            n0, pos0 = cover.get(k, (0, ''))
            if n0 >= ROLLIN_READ or (n0 >= 2 and pos0 in ('動詞', '形容詞', '助動詞')):
                continue
            # 長い並び（ROLLIN_SHORT 字を超える）では、助詞・用言の字（でんわ｜で｜よやく の で）も抜かない
            if b - a > ROLLIN_SHORT and pos0 in ('助詞', '動詞', '形容詞', '助動詞'):
                continue
            subs = ['']
            # 短い並びでは、近いキーへの打ち違い（1字の置き換え）も同じ形で見る。正しい文で出たので既定は抜きだけ（CN_LATTICE_SHIFT_SUB=1 で試す）
            if b - a <= ROLLIN_SHORT and not must and os.environ.get('CN_LATTICE_SHIFT_SUB') == '1':
                try:
                    from kana_layout import nearby_candidates
                    subs += [x for x, _dd in nearby_candidates(line[k], max_dist=1.0, include_phonetic=False)
                             if x != line[k] and _hira(x) and x != 'ー']
                except Exception:
                    pass
            for sub in subs:
                got = _rollin_try(line, k, sub, store, dict_index, cover)
                if got:
                    found.append((k, got[0], got[1], a, b, sub))
                    # 抜いた字の前後との入れ替わり（ともだ｜に｜ち → ともだちに）でも語が置けるなら、抜きか入れ替えか
                    # 決まらない。紫にする（2026-11-06 打つ順の入れ替えの束で、抜きが助詞を落とす誤り）。CN_LATTICE_ROLLIN_SWAPCHK=0
                    if not sub and os.environ.get('CN_LATTICE_ROLLIN_SWAPCHK') != '0':
                        # 抜いた字を前後3字までの別の所へ移しても（ねぼ｜し｜うた → ねぼうした）語が置けるなら決まらない
                        rest = line[:k] + line[k + 1:]
                        for j in range(max(a, k - 3), min(b, k + 4)):
                            if j in (k, k + 1) and j != k - 1:
                                continue
                            if j == k:
                                continue
                            jj = j if j < k else j - 1
                            if jj == k:
                                continue
                            moved = rest[:jj] + line[k] + rest[jj:]
                            if moved == line:
                                continue
                            try:
                                pl2, _d2 = propose(moved, store, dict_index)
                            except Exception:
                                continue
                            if any(p[0] <= jj + 1 and jj <= p[1] and p[1] - p[0] >= ROLLIN_READ and any(_kanji(c) for c in p[2]) for p in pl2):
                                found.append((jj, moved, pl2, a, b, 'move'))
                                break
            # 隣どうしの2字の打つ順の入れ替わり（りしょう → しりょう）。正しい文に紫が出たので既定は切（CN_LATTICE_SWAP=1 で試す）
            if (k + 1 < b and line[k + 1] != line[k] and _hira(line[k + 1]) and line[k + 1] not in 'ーゃゅょぁぃぅぇぉっ'
                    and not must and b - a <= ROLLIN_SHORT and os.environ.get('CN_LATTICE_SWAP') == '1'):
                n1, pos1 = cover.get(k + 1, (0, ''))
                if not (n1 >= ROLLIN_READ or (n1 >= 2 and pos1 in ('動詞', '形容詞', '助動詞'))):
                    got = _rollin_try(line, k, line[k + 1] + line[k], store, dict_index, cover, width=2)
                    if got:
                        found.append((k, got[0], got[1], a, b, line[k + 1] + line[k]))
    if not found:
        return None
    if any((f[3], f[4]) in explained_runs for f in found):
        if len(found) > 1 or found[0][5]:
            return None
        k, new, places, a, b, _sub = found[0]
        placed = new
        for s0, e0, face in sorted(places, reverse=True):
            placed = placed[:s0] + face + placed[e0:]
        base, cost = morphology.path_cost(line), morphology.path_cost(placed)
        if base is None or cost is None or base - cost < ROLLIN_EXPLAINED_GAIN:
            return None
        out = dict(result)
        out['odd_spans'] = [(a, b)]
        out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, 'かな1字の打ち違いかもしれない')]
        return out
    return _rollin_finish(line, result, found)


def _rollin_try(line, k, sub, store, dict_index, cover, width=1):
    """k から width 字を sub に替えた（'' なら抜いた）行で、替えた所をまたいで漢字の名詞が置けるなら (行, 置く語) を返す。"""
    new = line[:k] + sub + line[k + width:]
    try:
        places, _d = propose(new, store, dict_index)
    except Exception:
        return None
    # 抜いたなら替えた所は new の k の手前と k の間、替えたなら new[k]
    if sub:
        hit = [p for p in places if p[0] <= k < p[1] and p[1] - p[0] >= ROLLIN_READ and any(_kanji(c) for c in p[2])]
    else:
        hit = [p for p in places if p[0] < k < p[1] and p[1] - p[0] >= ROLLIN_READ and any(_kanji(c) for c in p[2])]
    # 置く語が、替えた字のほかに元の並びの長い語・用言の字（こ｜ください の くさ）を飲み込むなら採らない
    def swallows(p):
        for q in range(p[0], p[1]):
            if sub and k <= q < k + len(sub):
                continue
            oq = q if (sub or q < k) else q + 1
            n1, pos1 = cover.get(oq, (0, ''))
            if n1 >= ROLLIN_READ + 1 or (n1 >= 2 and pos1 in ('動詞', '形容詞', '助動詞')):
                return True
        return False
    hit = [p for p in hit if not swallows(p)]
    return (new, places) if hit else None


def _rollin_finish(line, result, found):
    a, b = found[0][3], found[0][4]
    if len(found) > 1:
        out = dict(result)
        out['odd_spans'] = [(a, b)]
        out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, 'かな1字の打ち違いかもしれない（直す所が決まらない）')]
        return out
    k, new, places, a, b, sub = found[0]
    import morphology
    placed = new
    for s0, e0, face in sorted(places, reverse=True):
        placed = placed[:s0] + face + placed[e0:]
    base, cost = morphology.path_cost(line), morphology.path_cost(placed)
    if base is None or cost is None or cost > base:
        return None
    if base - cost < ROLLIN_GAIN:
        # 並びの費用の下がりが小さい直しは決めずに紫（費用の下がりの小さい抜きに誤りが多い: 巻き込みの束 2026-11-06）
        out = dict(result)
        out['odd_spans'] = [(a, b)]
        out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, 'かな1字の打ち違いかもしれない')]
        return out
    ops = [o for o in difflib.SequenceMatcher(None, line, placed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'original': line, 'corrected': placed, 'changed': True,
                'details': list(result.get('details') or []) + [[line[k:k + max(1, len(sub))], sub, 'かな入力']]
                + [[new[s0:e0], f, '読みの区切り'] for s0, e0, f in places],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops],
                'unsure_spans': []})
    return out


def repair_line(line, result, store, dict_index):
    """result: ほかの補正の答え。かなのまま残った並び（ほかの補正が触っていない所）だけに置く。"""
    if not isinstance(result, dict):
        return result
    if result.get('odd_spans'):
        return _place_over_purple(line, result, store, dict_index)
    done = result.get('corrected') or line
    # かなだけで書いた行も、漢字で書くのが普通の名詞は漢字にする（うに 10-31 03:06Z「かなだけの行も、漢字にするべき
    # 部分は漢字に」。以前はかなだけの行を書くつもりのかなと見て触らなかった）
    try:
        places, doubts = propose(done, store, dict_index)
    except Exception:
        return result
    if not doubts or os.environ.get('CN_LATTICE_ROLLIN_ANY') != '0':
        got = _rollin_delete(line, result, store, dict_index)
        if got is not None:
            return got
    if not places:
        got = _yoon_slip(line, result)
        if got is not None:
            return got
        return _doubt_marks(line, result, done, doubts)
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    # ほかの補正が直した所には重ねない。ただし直した結果がかなのままで、置く語の中に収まる所（し゛かん → じかん の
    # 濁点の付け直し）は、直したかなの読みに漢字を置く
    def clash(p, x, y):
        if not (x < p[1] and p[0] < y):
            return False
        # 抜いただけの所（x == y: ぎ゜ょう → ぎょう の ゜ を抜いた）も、置く語の中なら同じ
        return not (p[0] <= x and y <= p[1] and x <= y and all(_hira(c) for c in done[x:y]))
    places = [p for p in places if not any(clash(p, x, y) for x, y in changed)]
    # 置く名詞のすぐ後ろに漢字が続き、つないだ形（結果＋式）が辞書の語でない所は、その名詞で決まらない（結婚式 の
    # 打ち違いを 結果式 にしていた・2026-11-06 かなの試験）。置かずに紫。CN_LATTICE_KANJI_AFTER=0
    if places and os.environ.get('CN_LATTICE_KANJI_AFTER') != '0':
        keepp, bad = [], []
        for p in places:
            if p[1] < len(done) and _kanji(done[p[1]]) and all(_kanji(c) for c in p[2]) \
                    and not _joined_word_ok(p[2], done, p[1], store, dict_index):
                bad.append((p[0], p[1]))
            else:
                keepp.append(p)
        if bad:
            places = keepp
            if not places:
                out = dict(result)
                out['odd_spans'] = list(result.get('odd_spans') or []) + bad
                return out
    if not places:
        return result
    # ほかの補正が迷った所（unsure）は、置く語でその所が全部埋まるときだけ置く（しょうひんばんごう → 商品番号）
    unsure = [tuple(u[:2]) for u in result.get('unsure_spans') or ()]
    # 行全体に掛かる迷い（もんだいがないかしらべる の 0〜行末）は、どこが迷いかを言っていない。置く所の確かめは
    # 下の行の自然さに任せる（かなだけの正しい行が 問題 にならず、かなのまま残っていた）。CN_LATTICE_UNSURE_WHOLE=0
    if unsure and os.environ.get('CN_LATTICE_UNSURE_WHOLE') != '0' and len(line) >= 2:
        unsure = [u for u in unsure if not (u[0] <= 0 and u[1] >= min(len(line), len(done)))]
    if unsure:
        lo, hi = min(p[0] for p in places), max(p[1] for p in places)
        if not all(lo <= u0 and u1 <= hi for u0, u1 in unsure):
            # 迷いが置く語に掛かって外にはみ出す所（ご｜ぜんちゅうはいそがしい）は、置いた後の行で迷いの所に残るかなが
            # どれも文法で説明できるときだけ置く。CN_LATTICE_UNSURE_EXPLAINED=0
            if os.environ.get('CN_LATTICE_UNSURE_EXPLAINED') == '0' or not all(
                    u0 < hi and lo < u1 for u0, u1 in unsure):
                return result
            try:
                import re
                import pos_grammar
                new_ = done
                for s_, e_, f_ in sorted(places, reverse=True):
                    new_ = new_[:s_] + f_ + new_[e_:]
                if not all(pos_grammar.explain_kana_run(m_.group(), after_kanji=m_.start() > 0 and not _hira(new_[m_.start() - 1]))
                           for m_ in re.finditer('[ぁ-ゖー]+', new_)):
                    return result
            except Exception:
                return result
    import morphology
    base = morphology.path_cost(done)
    new = done
    for s, e, face in sorted(places, reverse=True):
        new = new[:s] + face + new[e:]
    cost = morphology.path_cost(new)
    # 行の自然さは「置いて悪くならない」ことの確かめにだけ使う（格子の費用とは混ぜない）
    if base is None or cost is None or cost > base:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return result
    out = dict(result)
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + [[done[s:e], f, '読みの区切り'] for s, e, f in places],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops],
                'unsure_spans': []})
    # 置いた所のほかに表記の決まらない名詞があれば紫も残す（置けたから黙らない）。CN_LATTICE_AMBIG_PURPLE=0
    if doubts and os.environ.get('CN_LATTICE_AMBIG_PURPLE') != '0':
        keep = []
        for x, y in doubts:
            if any(x < p[1] and p[0] < y for p in places):
                continue
            d = sum(len(f) - (pe - ps) for ps, pe, f in places if pe <= x)
            if new[x + d:y + d] == done[x:y]:
                keep.append((x + d, y + d))
        if keep:
            out['odd_spans'] = list(out.get('odd_spans') or []) + keep
            out['face_doubt_spans'] = keep
    return out
