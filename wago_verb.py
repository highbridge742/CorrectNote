# -*- coding: utf-8 -*-
"""かなだけの行の和語の動詞を漢字に置く段（うに 2026-11-09 06:30Z 決め事カード「動詞は漢字」）。

11-01 の決まり（和語はかなのまま）を動詞についてだけ変える。和語の名詞・形容詞・ひらがなで書くのが普通の語
（いる・ある・する・なる・できる・いたす・くださる・いただく・もらう・くれる・あげる・おく・しまう・みる の補助の使い方）は
かなのまま。表記は、同じ読みの動詞の表記のうち、前の 名詞＋を/に/が の組が例文（tatoeba_pairs）に在るものが1つ
ならそれ、組が無ければ一般の文でいちばんよく使う表記が次の表記より GAP 以上よく使われるときだけ（はなす →
話す・離す・放す は決まらない＝かなのまま）。切り替え CN_WAGO_VERB_KANJI=0 で前のまま（何もしない）。
"""
import os

GAP = 80
DOMINANT = 5
COMMON = 470
_KANA_VERBS = {'ある', 'いる', 'する', 'なる', 'できる', 'いたす', 'くださる', 'もらう', 'くれる', 'あげる', 'おく',
               'しまう', 'みる', 'いう', 'やる', 'おる', 'ござる', 'いらっしゃる', 'おっしゃる', 'なさる', 'まいる',
               'いただく', 'さしあげる', 'もうす', 'おいでになる'}
_AUX_BEFORE = ('て', 'で')
_VERB_ONLY_NEXT = ('まし', 'ます', 'ませ', 'ましょ', 'て', 'た', 'たい')


def _hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' for c in s)


def kana_only(line):
    body = [c for c in line if not c.isspace()]
    return bool(body) and all('ぁ' <= c <= 'ゖ' or c in 'ー、。，．！？!?「」『』（）()…・〜' for c in body) \
        and any('ぁ' <= c <= 'ゖ' for c in body)


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _verb_faces(rd):
    import reading_lattice as lat
    lat.load()
    out = []
    for s, _l, _r, _c, pos in lat._table.get(rd, ()):
        if pos == '動詞' and any(_kanji(c) for c in s) and s not in out:
            out.append(s)
    try:
        import last_keystroke as LK
        from morphology import tokenize
        for f in LK._kanji_choices(rd, None, None) or ():
            if f in out or not any(_kanji(c) for c in f):
                continue
            t = list(tokenize(f))
            if len(t) == 1 and t[0].pos == '動詞':
                out.append(f)
    except Exception:
        pass
    return out


def _base(face):
    try:
        from morphology import tokenize
        t = list(tokenize(face))
        return t[0].base_form if len(t) == 1 and t[0].pos == '動詞' else None
    except Exception:
        return None


NOUN_RIVAL = 450   # 同じ読み（前後の字を足した読みも）に、これ以下の順位の漢字の名詞があれば動詞と決めない


def noun_rival(run, s, e, verb_rank=NOUN_RIVAL):
    """run の s:e（動詞と読んだ所）が、そのまま・前後に2字まで足した読みで、身近な漢字の名詞（いえ → 家・
    くる＋ま → 車）にも、置く動詞の表記より身近な名詞として読めるか。格子の切り方の迷いなので動詞と決めない。"""
    import reading_lattice as lat
    import ime_reconvert as R
    lat.load()
    for a in range(max(0, s - 2), s + 1):
        for b in range(e, min(len(run), e + 2) + 1):
            for f, _l, _r, _c, pos in lat._table.get(run[a:b], ()):
                if pos == '名詞' and any(_kanji(c) for c in f) and R._rank(f) < min(verb_rank, NOUN_RIVAL):
                    return True
    return False


_LAST_BY_FRAME = [False]



def choose(rd, prev_noun=None, prev_particle=None):
    """表記を1つ選ぶ（決まらなければ None）。前の 名詞＋助詞 の組で決めたときは _LAST_BY_FRAME[0] が True。"""
    import ime_reconvert as R
    _LAST_BY_FRAME[0] = False
    faces = _verb_faces(rd)
    if not faces:
        return None
    if prev_noun and prev_particle:
        try:
            import pair_choice
            tab = pair_choice._table()
            if tab:
                pairs = tab[0]
                cnt = sorted(((pairs.get('\t'.join((prev_particle, prev_noun, _base(f) or '')), 0), f) for f in faces),
                             reverse=True)
                cnt = [c for c in cnt if c[0] > 0]
                # 組が例文に在る表記が1つか、いちばん多い表記が次の DOMINANT 倍以上なら、それに決める（本を読む 509・選ぶ 8）
                if cnt and (len(cnt) == 1 or cnt[0][0] >= DOMINANT * cnt[1][0]):
                    _LAST_BY_FRAME[0] = True
                    return cnt[0][1]
                if len(cnt) > 1:
                    return None
        except Exception:
            pass
    ranked = sorted(faces, key=R._rank)
    best = R._rank(ranked[0])
    if best > COMMON:
        return None
    if len(ranked) > 1 and R._rank(ranked[1]) < best + GAP:
        # 一般の順位で差が小さいとき（うち → 打ち 463・撃ち 518）は、例文の組の数を表記の基本形ごとに足して比べる
        # （打つ 102・撃つ 18）。いちばん多いのが次の DOMINANT 倍以上で、TOTAL_MIN 以上あれば決める
        if os.environ.get('CN_WAGO_VERB_TOTALS') == '0':
            return None
        tot = _base_totals()
        cnt = sorted(((tot.get(_base(f) or '', 0), f) for f in faces), reverse=True)
        if cnt and cnt[0][0] >= TOTAL_MIN and (len(cnt) == 1 or cnt[0][0] >= DOMINANT * max(cnt[1][0], 1)):
            if R._rank(cnt[0][1]) <= COMMON:
                return cnt[0][1]
        return None
    return ranked[0]


TOTAL_MIN = 20
_TOTALS = []


def _base_totals():
    """例文の 助詞＋名詞＋動詞 の組の数を、動詞の基本形ごとに足したもの。"""
    if _TOTALS:
        return _TOTALS[0]
    out = {}
    try:
        import pair_choice
        tab = pair_choice._table()
        for k, v in (tab[0] if tab else {}).items():
            parts = k.split('\t')
            if len(parts) == 3:
                out[parts[2]] = out.get(parts[2], 0) + v
    except Exception:
        pass
    _TOTALS.append(out)
    return out


_CASE_NEXT = ('で', 'の', 'を', 'が', 'は', 'に', 'も', 'と')


def _noun_renyou(run):
    """並びの頭が かなの名詞＋動詞の連用形＋助詞（かな｜うち｜での）なら、連用形の名詞化（かな打ち）として
    (開始, 終了, 表記) を返す。格子は連用形の名詞化を持たないので 金内・蚊な に読む。連用形の読みがそれだけで
    ふつうの名詞（かき → 柿）なら名詞と読めるので見ない（非自立の名詞 うち・ところ は前の名詞の後ろには来ない）。"""
    import reading_lattice as lat
    from morphology import tokenize
    for s in range(2, len(run) - 2):
        try:
            left = list(lat.best(run[:s]).words)
        except Exception:
            continue
        if len(left) != 1 or left[0][2] != '名詞':
            continue
        # 前の名詞は ふつうの名詞だけ（全部・今日・みんな の後ろの うち は 家・内）
        lt = list(tokenize(left[0][0]))
        if len(lt) != 1 or (lt[0].pos_sub or '') not in ('一般', 'サ変接続'):
            continue
        for e in range(s + 2, min(len(run), s + 4)):
            rd = run[s:e]
            if run[e] not in _CASE_NEXT or rd[-1] not in 'いきしちにひみりぎじびぴえけせてねへめれげぜでべぺ':
                continue
            tt = list(tokenize(rd))
            if len(tt) == 1 and tt[0].pos == '名詞' and not (tt[0].pos_sub or '').startswith('非自立'):
                continue
            pick = choose(rd)
            if not pick or not any(_kanji(c) for c in pick):
                continue
            b = _base(pick)
            if not b or b in _KANA_VERBS:
                continue
            return (s, e, pick)
    return None


def _odd_parse(words):
    """格子の読みが文として当てにならない並びか: フィラー（おもしれえ の え）・動詞の後ろの1字の動詞（埋め｜得）。"""
    for k, w in enumerate(words):
        face, rd, pos = w[0], w[1], w[2]
        if pos == 'フィラー':
            return True
        if pos == '動詞' and len(rd) == 1 and k > 0 and words[k - 1][2] == '動詞':
            return True
    return False


def repair_line(line, result):
    if os.environ.get('CN_WAGO_VERB_KANJI') == '0' or not isinstance(result, dict) or not kana_only(line):
        return result
    done = result.get('corrected') or line
    import reading_lattice as lat
    import difflib
    # 元の行と同じ字の所（直しの入っていない所）だけを見る
    same = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] == 'equal']
    new = done
    reps = []
    i = 0
    while i < len(done):
        if not ('ぁ' <= done[i] <= 'ゖ'):
            i += 1
            continue
        j = i
        while j < len(done) and 'ぁ' <= done[j] <= 'ゖ':
            j += 1
        run = done[i:j]
        # くだけた形の形容詞（おもしれえ）は元の形容詞（おもしろい）に戻して読む。字の数は同じなので位置はずれない
        adj = []
        try:
            import colloquial_adj
            run, adj = colloquial_adj.normalize(run)
        except Exception:
            adj = []
        try:
            r = lat.best(run)
            words = list(r.words) if r else []
        except Exception:
            words = []
        at = i
        prev = []
        # 解析（morphology）で並びの中の語の頭になる位置。格子の動詞がそこから始まらない（かんが｜える: 解析は かんがえる で
        # 1語）なら、語の途中を切った読みなので置かない（2026-11-09 うに「かんがえる が補正される」→ かんが得る）。
        # CN_WAGO_VERB_TOKEN_EDGE=0 で前のまま
        heads = None
        if os.environ.get('CN_WAGO_VERB_TOKEN_EDGE') != '0':
            try:
                from morphology import tokenize as _tok
                heads = {i + t.start for t in _tok(run)}
            except Exception:
                heads = None
        if os.environ.get('CN_WAGO_VERB_ODD_PARSE') != '0' and _odd_parse(words):
            words = []   # くだけた言い方（おもしれえ → 苧/も/知れ/え）は格子の読みが当てにならないので置かない
        for k, w in enumerate(words):
            face, rd, pos = w[0], w[1], w[2]
            s, e = at, at + len(rd)
            at = e
            if pos != '動詞' or len(rd) < 2 or not any(a <= s and e <= b for a, b in same) \
                    or (heads is not None and s not in heads) \
                    or any(a < e - i and s - i < b for a, b, _w in adj):
                prev.append((face, rd, pos, s, e))
                continue
            before = prev[-1] if prev else None
            # て/で の後ろの動詞は補助の使い方（よんでいる）。ただし で の前が名詞なら格助詞（いえでまつ）
            aux_te = before and before[2] in ('助詞',) and before[1] in _AUX_BEFORE
            if aux_te and before[1] == 'で' and len(prev) >= 2 and prev[-2][2] == '名詞' \
                    and os.environ.get('CN_WAGO_VERB_DE_CASE') != '0':
                aux_te = False
            if aux_te:
                prev.append((face, rd, pos, s, e))
                continue
            bf = _base(face) if any(_kanji(c) for c in face) else None
            if bf is None:
                try:
                    from morphology import tokenize
                    tt = list(tokenize(rd))
                    bf = tt[0].base_form if len(tt) == 1 and tt[0].pos == '動詞' else None
                except Exception:
                    bf = None
            hb = None
            for f in _verb_faces(rd):
                hb = hb or _base(f)
            kb = None
            try:
                from morphology import tokenize
                tt = list(tokenize(rd + 'ます')) if not rd.endswith(('る', 'う', 'く', 'す', 'つ', 'ぬ', 'ぶ', 'む', 'ぐ')) else list(tokenize(rd))
                kb = tt[0].base_form if tt and tt[0].pos == '動詞' else None
            except Exception:
                pass
            if kb in _KANA_VERBS:
                prev.append((face, rd, pos, s, e))
                continue
            pn = pp = None
            if before and before[2] == '助詞' and before[1] in ('を', 'に', 'が') and len(prev) >= 2:
                pn, pp = prev[-2][0], before[1]
                # 前の名詞はもう置いた行の表記（手紙）で引く
                got = done[prev[-2][3]:prev[-2][4]]
                pn = got if any(_kanji(c) for c in got) else pn
            # 助詞が並びの頭で、すぐ前が漢字の名詞（本｜をよんで）なら、その名詞で組を引く
            if before and before[2] == '助詞' and before[1] in ('を', 'に', 'が') and len(prev) == 1 and i > 0 \
                    and _kanji(done[i - 1]):
                try:
                    from morphology import tokenize
                    tk = [t for t in tokenize(done[:i]) if t.end == i and t.pos == '名詞']
                    if tk:
                        pn, pp = tk[-1].surface, before[1]
                except Exception:
                    pass
            pick = choose(rd, pn, pp)
            # 組（手紙を書く）で決めた表記は、同じ読みの名詞（下記）より確か。名詞との比べは組の無い時だけ
            # すぐ後ろが動詞にしか付かない語（まし・ませ・て・た）なら名詞とは読めないので、名詞との比べはしない
            nxt = words[k + 1] if k + 1 < len(words) else None
            verb_only_next = (nxt is not None and nxt[2] in ('助動詞', '助詞') and nxt[1] in _VERB_ONLY_NEXT
                              and os.environ.get('CN_WAGO_VERB_NEXT') != '0')
            if pick and not _LAST_BY_FRAME[0] and not verb_only_next and os.environ.get('CN_WAGO_VERB_NOUN_RIVAL') != '0':
                import ime_reconvert as _R
                if noun_rival(run, s - i, e - i, _R._rank(pick)):
                    pick = None
            if pick and pick != rd:
                reps.append((s, e, pick))
            prev.append((face, rd, pos, s, e))
        if not any(i <= a < j for a, _b, _f in reps) and os.environ.get('CN_WAGO_VERB_COMPOUND') != '0':
            got = _noun_renyou(run)
            if got and any(a <= i + got[0] and i + got[1] <= b for a, b in same):
                reps.append((i + got[0], i + got[1], got[2]))
        i = j
    if not reps:
        return result
    for s, e, f in sorted(reps, reverse=True):
        new = new[:s] + f + new[e:]
    out = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': list(result.get('details') or []) + [[done[s:e], f, '和語の動詞を漢字に'] for s, e, f in reps]})
    return out
