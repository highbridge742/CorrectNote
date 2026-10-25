# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
連用形の後ろの尾の1打ずれ（補正担当・2026-10-25。未解決タブ カレーをつくりのす→つくります）。

かなの並びが「動詞の連用形＋説明の付かない短い尾」（つくり｜のす）で、尾の1字を隣のキーに替えると
助動詞・助詞だけの尾（ます・ました・たい・て…）になり、並び全体がかなの文法で説明できるなら、その形に直す。
  - 動詞の部分（つくり）はそのまま。替えるのは尾の1字だけ（隣のキー・入力方式の配列）。
  - 候補が1つのときだけ置く。複数なら触らない（迷いはほかの印に任せる）。
  - 置いた所に重なっていた紫（元の行の位置）は外す。
語彙の読みは終止形（つくる）しか持たないので、芯の再構築の似た読みでは つくります に届かない。
辞書にも つくります の1語は無い。だから連用形＋尾の形で見る。特定の語は名指ししない。
"""
import difflib

MAX_TAIL = 4      # 尾のかなの長さ（字）
MIN_RUN = 4       # 見るかなの並びの長さ


def _hira(ch):
    return 'ぁ' <= ch <= 'ゖ'


def _kana_runs(text):
    out, i = [], 0
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


def _explained(run):
    try:
        import pos_grammar
        return bool(pos_grammar.explain_kana_run(run))
    except Exception:
        return True


def _aux_tail_only(tokens):
    return bool(tokens) and all(t.pos in ('助動詞', '助詞') for t in tokens)


def propose(text, input_method='kana'):
    """[(start, end, 直した並び)]。候補が1つに決まる並びだけ。"""
    try:
        import morphology
        from kana_layout import nearby_candidates
    except Exception:
        return []
    out = []
    for a, b in _kana_runs(text):
        run = text[a:b]
        # 漢字の直後から始まる並び（忘れ｜ていた の れていた）は送りがなの続き。動詞の頭がかなで完結している並びだけ
        if a > 0 and ('一' <= text[a - 1] <= '鿿' or text[a - 1] == '々'):
            continue
        if _explained(run):
            continue
        toks = list(morphology.tokenize(run))
        # 並びの中の「連用形の動詞＋尾（並びの終わりまで）」を探す（ーを｜つくり｜のす）
        head = None
        for i, t in enumerate(toks[:-1]):
            if (t.pos == '動詞' and t.infl_form == '連用形' and t.has_reading
                    and len(t.surface) >= 2 and 1 <= len(run) - t.end <= MAX_TAIL):
                head = (i, t)
                break
        if head is None:
            continue
        i, h = head
        tail = run[h.end:]
        # 元の尾が既に助動詞・助詞だけ（した・ていた・てくれた）なら、正しい形。触らない
        if _aux_tail_only(toks[i + 1:]):
            continue
        before = [(t.surface, t.pos) for t in toks[:i]]
        cands = set()
        for k, ch in enumerate(tail):
            try:
                alts = nearby_candidates(ch, max_dist=1.0, include_phonetic=False)
            except Exception:
                alts = ()
            for alt, dist in alts:
                # 隣のキー1手だけ（濁点・半濁点の付け違い た→だ は打鍵のずれではないので見ない）
                if alt == ch or dist > 1.0 or dist < 0.9:
                    continue
                cand = run[:h.end] + tail[:k] + alt + tail[k + 1:]
                ctoks = list(morphology.tokenize(cand))
                if len(ctoks) < i + 2 or [(t.surface, t.pos) for t in ctoks[:i]] != before:
                    continue
                if ctoks[i].surface != h.surface or ctoks[i].pos != '動詞' or ctoks[i].end != h.end:
                    continue
                # 尾は連用形に付く助動詞から始まり、助動詞・助詞だけ（ます・ました・たい）。助詞から始まる尾（のか）は別の形
                if not _aux_tail_only(ctoks[i + 1:]) or ctoks[i + 1].pos != '助動詞':
                    continue
                cands.add(cand)
        if len(cands) == 1:
            out.append((a, b, next(iter(cands))))
    return out


def _to_original(line, done, s, e):
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= s and e <= i2:
            return s - i1 + j1, e - i1 + j1
    return None


def repair_line(line, result, decided=(), input_method='kana'):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, input_method)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    new, details, cleared = done, [], []
    for s, e, cand in sorted(marks, reverse=True):
        if any(x < e and s < y for x, y in changed):
            continue
        org = _to_original(line, done, s, e)
        if org is None or any(x < org[1] and org[0] < y for x, y in (decided or ())):
            continue
        new = new[:s] + cand + new[e:]
        details.append([done[s:e], cand, '連用形の尾'])
        cleared.append(org)
    if new == done:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + details,
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    # 置いた並びに重なる紫・迷い（元の行の位置）は外す。重なる印は「説明の付かないかな述語」の印で、置いた形がその答え
    for key in ('odd_spans', 'unsure_spans'):
        out[key] = [sp for sp in (result.get(key) or ()) if not any(a < sp[1] and sp[0] < b for a, b in cleared)]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ()) if not any(a < r[1] and r[0] < b for a, b in cleared)]
    return out
