"""既知の頭＋紫の2字の漢語（一括＋流力）を、頭の熟語の門（corrector._fix_known_head_compound・48-RK）と同じ門で、
同点の候補を全部比べて直す段（head_tie・2026-11-09 手分けB）。

corrector の 48-RK は、残りの読みの候補（find_known_readings_flex）の**先頭から**門を通った最初の1つで決める。
語彙によって 1手の候補が同点で並ぶと（りゅうりょく → ちゅうりょく・にゅうりょく が 1.4 で並び、ちゅうりょく が先）、
先頭の 注力 だけが試され、頭と組まないので None になり、2番の 入力 は見られない。並べ方で答えが変わる。
ここでは紫の所（漢字2字・前に既知の2字の漢語）について、一番近い同点の候補を**全部**同じ門に通し、
通ったのが1つの表記だけなら直す。2つ以上なら決めない（紫のまま）。

門（48-RK と同じもの）:
  頭      紫の所の直前の漢字2字・段 ≤ 2（kango_tier）・その前は漢字でない
  残り    紫の所の読み（記録 → 語の読み）を 1手以内（edits ≤ 1・同じ長さ）の読みに
  漢字    corrector._convert_odd_kana_run で2字の漢語・段 ≤ 2
  複合    semantic_roles.nominal_compound_support(頭, 残り)・oddness.is_odd_run(頭＋残り) が []
corrector.py は CODE_SHA256 で固定なので触らない。CN_HEAD_TIE=0 で前のまま。
"""
import os

MAX_DIST = 1.6      # corrector._fix_known_head_compound の max_dist と同じ


def _on():
    return os.environ.get('CN_HEAD_TIE') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c in '々〆'


def _faces(rds, head, store, dict_index, tokenize_fn):
    import corrector as C
    from vocabulary import find_known_readings_flex
    from semantic_roles import nominal_compound_support
    import oddness
    cands = []
    for rd0 in rds:
        try:
            got = list(find_known_readings_flex(rd0, store, MAX_DIST))
        except Exception:
            got = []
        cands += [(d, rd) for rd, d, ed in got if rd and ed <= 1 and len(rd) == len(rd0)]
    if not cands:
        return set()
    lo = min(d for d, _r in cands)
    out = set()
    for d, rd in cands:
        if d != lo:
            continue
        try:
            g = C._convert_odd_kana_run(rd, store, dict_index)
        except Exception:
            g = None
        tk = g[0] if isinstance(g, tuple) else g
        if not tk or len(tk) != 2 or not all(_kanji(c) for c in tk) or C._kango_tier_of(tk) > 2:
            continue
        if not nominal_compound_support(head, tk):
            continue
        try:
            if oddness.is_odd_run(head + tk, tokenize_fn, store=store, dict_index=dict_index):
                continue
        except Exception:
            continue
        out.add(tk)
    return out


def repair_line(line, result, store, dict_index, decided=()):
    """紫の所を直した result か、そのままの result。"""
    if not _on() or not isinstance(result, dict) or store is None:
        return result
    done = result.get('corrected') or line
    spans = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    for a, b in spans:
        if b - a != 2 or a < 2 or not all(_kanji(c) for c in done[a:b]):
            continue
        head = done[a - 2:a]
        if not all(_kanji(c) for c in head) or (a >= 3 and _kanji(done[a - 3])) or (b < len(done) and _kanji(done[b])):
            continue
        if any(x < b and a < y for x, y in [tuple(d[:2]) for d in (decided or ())]):
            continue
        try:
            import corrector as C
            import odd_respell as O
            if C._kango_tier_of(head) > 2:
                continue
            sr = O._span_reading(done, a, b, dict_index)
            if not sr or (sr[0], sr[1]) != (a, b):
                continue
            fn = getattr(store, '_tokenize_fn', None) or C.make_tokenizer(store)
            faces = _faces(sr[2], head, store, dict_index, fn)
        except Exception:
            continue
        faces.discard(done[a:b])
        if len(faces) != 1:
            continue
        tk = faces.pop()
        out = dict(result)
        new = done[:a] + tk + done[b:]
        out['corrected'] = new
        out['changed'] = new != line
        out['odd_spans'] = [sp for sp in (result.get('odd_spans') or ()) if tuple(sp[:2]) != (a, b)]
        if 'odd_reasons' in out:
            out['odd_reasons'] = [r for r in (out.get('odd_reasons') or ()) if tuple(r[:2]) != (a, b)]
        out['details'] = list(result.get('details') or ()) + [(done[a - 2:b], head + tk, '既知の頭の熟語の打ち違い')]
        import difflib
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out['spans'] = [[o[3], o[4]] for o in ops]
        out['original_spans'] = [[o[1], o[2]] for o in ops]
        return out
    return result
