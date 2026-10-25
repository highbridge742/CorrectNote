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
        starts = {0} | {t.end for t in morphology.tokenize(text) if t.pos in ('助詞', '記号')}
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
            if not explained:
                a, kana = p, text[p:b]
            # 頭から説明の付く並び（は｜すいぞくかんに）は書くつもりのかな。中の助詞の後ろ（くかんに）だけを見ない
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
            own = set(LK._own_faces(rd, store))
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


def repair_line(line, result, store, dict_index):
    """result: ほかの補正の答え。かなのまま残った並び（ほかの補正が触っていない所）だけに置く。"""
    if not isinstance(result, dict) or result.get('odd_spans') or result.get('unsure_spans'):
        return result
    done = result.get('corrected') or line
    # 行に漢字が1つも無い（かなだけで書いた行）なら、書くつもりのかなと見て触らない。ほかの補正が漢字を置いた
    # 行（間違いのほせい）だけ、残りの並びを見る
    if not any(_kanji(c) for c in done):
        return result
    try:
        places, doubts = propose(done, store, dict_index)
    except Exception:
        return result
    if not places:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    places = [p for p in places if not any(x < p[1] and p[0] < y for x, y in changed)]
    if not places:
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
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
