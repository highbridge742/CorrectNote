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

MIN_RUN = 3            # 見るかなの並びの長さ（字）
MIN_WORD = 2           # 置く語の読みの長さ
SEG_MARGIN = 800       # 1番と2番の切り方の費用の差がこれ未満なら迷い（紫）
_CONTENT_POS = ('名詞',)   # 置く語は名詞だけ（動詞・形容詞のかなは書くつもりのかなが多い: ひいて・こされ・ふせ。2026-10-25 測り）


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
    return [f for f in faces if f in own or (not LK._not_everyday_kango(f) and LK._kango_reads_as(f, rd))], own


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
        if nxt is not None and not (nxt[4] == '助詞' or (nxt[4] == '助動詞' and nxt[2] in _COPULA) or suru):
            return False
        if prev == 'を' and (nxt is None or nxt[4] != '助詞'):
            return False
        return True

    while n < len(spans):
        s, e, face, rd, pos = spans[n]
        if pos != '名詞' or not any(_kanji(c) for c in face):
            if pos == '名詞' and len(rd) >= MIN_WORD:
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
            if len(pusual) == 1 and not pother and len(nusual) >= 2:
                doubts.append((a + s, a + spans[n + 1][1]))
                return []
        toks = list(tokenize(rd))
        # かなで書くのが普通の語（副詞・副詞にもなる名詞・形容動詞の語幹: だいたい・いちばん・きれい）もかなのまま
        if len(toks) == 1 and (toks[0].pos == '副詞' or any(k in (toks[0].pos_sub or '') for k in
                                                         ('非自立', '代名詞', '数', '副詞可能', '形容動詞語幹'))):
            n += 1
            continue
        faces, own = _everyday_faces(rd, store, dict_index, LK)
        usual = [f for f in faces if f in own or ime_reconvert._rank(f) <= COMMON_FACE]
        # ほかの表記も一般に使われる語（はし → 橋・箸・端）は決まらない
        others = [f for f in faces if f not in usual and ime_reconvert._rank(f) <= OTHER_FACE]
        if len(usual) != 1 or others or not fits(n, n):
            return []
        out.append((a + s, a + e, usual[0]))
        n += 1
    return out


def _inflected_here(s, e, toks):
    """[s, e) が、行の解析で ちょうど 用言＋助動詞（し｜ない・いたく｜ない）に切れているか。かなの文法の説明が用言と
    助動詞の並びで、格子だけが同じ読みの名詞（しない → 市内）に組んだ所は、書くつもりの用言のかな（2026-11-02 うに
    「しないデータ」が名詞に替わった）。名詞を置かない。"""
    inside = [t for t in toks if s <= t.start and t.end <= e]
    if not inside or inside[0].start != s or inside[-1].end != e:
        return False
    if any(t.start < s < t.end or t.start < e < t.end for t in toks):
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
    # 助詞・助動詞だけに切れる所（ない｜か｜と の かと）を、格子が同じ読みの名詞（過渡）に組んだ形も書くつもりのかな
    return all(t.pos in ('助詞', '助動詞') for t in inside)


def propose(text, store, dict_index, surrounding=()):
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
    except Exception:
        return [], []
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
            places.extend(x for x in _explained_nouns(a, spans, store, dict_index, LK, text[a - 1:a] if a else '', doubts)
                          if not _inflected_here(x[0], x[1], toks_all))
            continue
        for s, e, face, rd, pos in spans:
            if not any(_kanji(c) for c in face):
                # かなのままの内容の語（すいぞ｜区間 の すいぞ）が残る切り方は、切り方そのものが怪しい。置かない
                if pos not in ('助詞', '助動詞') and len(rd) >= MIN_WORD:
                    whole = False
                    break
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
            faces = [f for f in faces if f in own or (not LK._not_everyday_kango(f) and LK._kango_reads_as(f, rd))]
            if not faces:
                whole = False
                break
            chosen = faces[0]
            # 格子の表記と候補の先頭の漢字が食い違うなら、区切りは同じでも語が決まらない＝置かない
            if {c for c in chosen if _kanji(c)} != {c for c in face if _kanji(c)}:
                whole = False
                break
            run_places.append((a + s, a + e, chosen))
        if whole:
            places.extend(run_places)
    return places, doubts


def _doubt_marks(line, result, done, doubts):
    """置けなかったかなの名詞の組（表記が決まらない）に紫。ほかの補正が触った所・紫の所には付けない。"""
    if not doubts or done != line:
        return result
    out = dict(result)
    out['odd_spans'] = list(result.get('odd_spans') or []) + [(x, y) for x, y in doubts]
    # 読みは合っていて表記だけ決まらない紫。打ち違いの戻し（odd_respell）は当てない（読みの1打を替えた別の語にしない）
    out['face_doubt_spans'] = [(x, y) for x, y in doubts]
    return out


def repair_line(line, result, store, dict_index):
    """result: ほかの補正の答え。かなのまま残った並び（ほかの補正が触っていない所）だけに置く。"""
    if not isinstance(result, dict) or result.get('odd_spans'):
        return result
    done = result.get('corrected') or line
    # かなだけで書いた行も、漢字で書くのが普通の名詞は漢字にする（うに 10-31 03:06Z「かなだけの行も、漢字にするべき
    # 部分は漢字に」。以前はかなだけの行を書くつもりのかなと見て触らなかった）
    try:
        places, doubts = propose(done, store, dict_index)
    except Exception:
        return result
    if not places:
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
    if not places:
        return result
    # ほかの補正が迷った所（unsure）は、置く語でその所が全部埋まるときだけ置く（しょうひんばんごう → 商品番号）
    unsure = [tuple(u[:2]) for u in result.get('unsure_spans') or ()]
    if unsure:
        lo, hi = min(p[0] for p in places), max(p[1] for p in places)
        if not all(lo <= u0 and u1 <= hi for u0, u1 in unsure):
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
    return out
