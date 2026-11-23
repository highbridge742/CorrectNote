# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""前の字に付けられない ゛゜（しが゛・かぜ゛か・ちすで゛）を、補正が黙って消した行の見直し。

なぜ
----
かな入力の ゛ は1つのキーなので、隣の字と打つ順が入れ替わると、付く字の1つ後ろ（じが → しが゛）や1つ前（かぜが →
かぜ゛か）に浮く。2026-11-21 補正担当の作り例（新しい40文・600行）で、こうした ゛ を消しただけの行（しがおおきく・
かぜかつよい）が 11 行あった（Fable 5.2 の意見: 消さずに入れ替えの2通りだけ試す）。消すのは余分な1打のときだけ正しい。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（かな入力の行だけ）。
1. 打った行で、直前の字に付けられない ゛゜ を探す（付いた字に重ねた が゛ も含む）。
2. 答えの読みがその ゛゜ を消しただけ（前後の字はそのまま）なら、3つの形を格子（reading_lattice.best）の費用で比べる:
   消す・2つ前の字に付ける（入れ替え: し が ゛ → じ が）・次の字に付ける（入れ替え: ぜ ゛ か → ぜ が）。
   前の2字の打つ順も入れ替わった形（た こ ま ゛ → たまご）も比べる。答えが ゛゜ の周りを別の形に書き換えたときは、
   その答えの読みも候補に入れる（CN_STRAY_MARK_ANSWER=0 で外す）。
3. 入れ替えの形が他の形より MARGIN 以上軽ければ、その形の行を補正に通し直してそれにする。消す形が MARGIN 以上
   軽ければ今の答えのまま。どれとも決まらなければ打った行に戻し、その ゛゜ の所を紫にする（迷ったら紫）。
入れ替えの形が無い（い゛ のように前後どちらにも付かない）行は今まで通り。切り替え: CN_STRAY_MARK_GUARD=0 で前のまま。
特定の語や文字列には合わせない。
"""
import difflib
import functools
import os
import unicodedata

MARGIN = 1000   # 浮いた濁点の脱字の段（FLOAT_MARK_MARGIN）と同じ線。2026-11-21 作り例の濁点の298行で確かめた
_orig = {}
_BUSY = []
_KT = {c: c - 0x60 for c in range(0x30A1, 0x30F7)}


def _reading(text):
    from morphology import tokenize
    return ''.join((t.reading if t.has_reading else t.surface) for t in tokenize(text)).translate(_KT)


def _join(ch, mark):
    x = unicodedata.normalize('NFC', ch + mark)
    return x if len(x) == 1 and 'ぁ' <= x <= 'ゖ' else None


def stray_at(line):
    """直前の字に付けられない ゛゜ の位置（最初の1つ）。無ければ None"""
    for m, ch in enumerate(line):
        if ch not in '゛゜':
            continue
        mark = '゙' if ch == '゛' else '゚'
        if m == 0 or _join(line[m - 1], mark) is None:
            return m
    return None


def candidates(line, m):
    mark = '゙' if line[m] == '゛' else '゚'
    out = {'drop': line[:m] + line[m + 1:]}
    if m >= 2 and 'ぁ' <= line[m - 1] <= 'ゖ':
        x = _join(line[m - 2], mark)
        if x:
            out['back'] = line[:m - 2] + x + line[m - 1] + line[m + 1:]
    if m >= 2 and 'ぁ' <= line[m - 1] <= 'ゖ' and 'ぁ' <= line[m - 2] <= 'ゖ':
        # 前の2字の打つ順も入れ替わった形（た こ ま ゛ → た ま ご）
        x = _join(line[m - 2], mark)
        if x and line[m - 1] != line[m - 2]:
            out['swap2'] = line[:m - 2] + line[m - 1] + x + line[m + 1:]
    if m + 1 < len(line):
        x = _join(line[m + 1], mark)
        if x:
            out['fwd'] = line[:m] + x + line[m + 2:]
    return out


def _cost(text):
    import reading_lattice as lat
    r = lat.best(text)
    return None if r is None else r.cost


def _dropped(line, m, out):
    """答えの読みが、その ゛゜ を消しただけで前後の字（2つ前〜次）はそのままか"""
    drop = line[:m] + line[m + 1:]
    rd = _reading(out)
    for tg, a, b, _c, _d in difflib.SequenceMatcher(None, drop, rd, autojunk=False).get_opcodes():
        if tg != 'equal' and a < m + 1 and max(m - 2, 0) < max(b, a + 1):
            return False
    return True


class _Undecided(Exception):
    pass


def _touches(line, m, out):
    """答えの読みが ゛゜ の所（2つ前〜次の字）を書き換えたか"""
    rd = _reading(out)
    for tg, a, b, _c, _d in difflib.SequenceMatcher(None, line, rd, autojunk=False).get_opcodes():
        if tg != 'equal' and a < m + 2 and max(m - 2, 0) < max(b, a + 1):
            return True
    return False


def _from_candidate(line, m, r2):
    fixed = r2.get('corrected') or line
    out = dict(r2)
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']

    def mv(xs):
        return [(a + (a >= m), b + (b > m)) + tuple(x[2:]) for x in xs or () for a, b in [tuple(x[:2])]]
    out.update({'original': line, 'corrected': fixed, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [[line[max(m - 2, 0):m + 2], fixed, '浮いた濁点の入れ替え']],
                'odd_spans': mv(r2.get('odd_spans')), 'odd_reasons': mv(r2.get('odd_reasons'))})
    out.pop('unsure_spans', None)
    return out


def correct_line(line, store, *a, **k):
    r = _orig['correct_line'](line, store, *a, **k)
    if os.environ.get('CN_STRAY_MARK_GUARD') == '0' or not isinstance(line, str) or not isinstance(r, dict) or _BUSY:
        return r
    im = k.get('input_method', a[2] if len(a) > 2 else 'kana')
    if im != 'kana':
        return r
    try:
        m = stray_at(line)
        if m is None:
            return r
        out = r.get('corrected') or line
        if out == line:
            return r
        cs = candidates(line, m)
        if not _dropped(line, m, out):
            # 答えが ゛゜ の周りを別の形に書き換えた（ととい゛た → と退いた）なら、その答えの読みも候補の1つとして比べる
            if os.environ.get('CN_STRAY_MARK_ANSWER') == '0' or not _touches(line, m, out):
                return r
            cs = dict(cs)
            cs['answer'] = _reading(out)
            cs.pop('drop', None) if cs['answer'] == cs.get('drop') else None
        elif len(cs) < 2:
            # 前後どちらにも付かない ゛゜ を消した形が語で切れなければ、消さずに紫
            if os.environ.get('CN_STRAY_MARK_ANSWER') != '0' and _cost(cs['drop']) is None:
                raise _Undecided()
            return r
        costs = sorted((c, name) for name, t in cs.items() for c in [_cost(t)] if c is not None)
        if 'answer' in cs:
            # 答えの書き換えは補正が選んだもの。入れ替えの形が答えより MARGIN 以上軽いときだけ替え、迷っても戻さない
            ca = next((c for c, n in costs if n == 'answer'), None)
            alt = [(c, n) for c, n in costs if n not in ('answer', 'drop')]
            if ca is None or not alt or alt[0][0] > ca - MARGIN or (len(alt) > 1 and alt[1][0] - alt[0][0] < MARGIN):
                return r
            costs = alt[:1]
        if not costs:
            raise _Undecided()
        best_c, best = costs[0]
        clear = len(costs) == 1 or costs[1][0] - best_c >= MARGIN
        if clear and best in ('drop', 'answer'):
            return r
        if clear:
            _BUSY.append(1)
            try:
                r2 = _orig['correct_line'](cs[best], store, *a, **k)
            finally:
                _BUSY.pop()
            if isinstance(r2, dict):
                return _from_candidate(line, m, r2)
            return r
    except _Undecided:
        pass
    except Exception:
        return r
    # 決まらない: 打った行に戻し、浮いた ゛゜ の所を紫に（他の書き換えの所も紫にして、直しを捨てたまま紫の無い所を作らない）
    back = dict(r)
    back.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': []})
    span = (max(m - 2, 0), m + 1) if ('back' in cs or 'swap2' in cs) else (m - 1, min(m + 2, len(line)))
    if ('back' in cs or 'swap2' in cs) and 'fwd' in cs:
        span = (max(m - 2, 0), min(m + 2, len(line)))
    why_t = '付く字が決められない濁点・半濁点です。前後の字と打つ順が入れ替わったかもしれません'
    odd, why = [span], [span + (why_t,)]
    try:
        rd = _reading(out)
        for o in difflib.SequenceMatcher(None, line, rd, autojunk=False).get_opcodes():
            if o[0] == 'equal':
                continue
            a_, b_ = o[1], max(o[2], o[1] + 1)
            if not any(x[0] < b_ and a_ < x[1] for x in odd):
                odd.append((a_, b_))
                why.append((a_, b_, '直し先を決められず元の語に戻しました。打ち違いかもしれません'))
    except Exception:
        pass
    back['odd_spans'] = sorted(odd)
    back['odd_reasons'] = why
    return back


def install():
    if _orig or os.environ.get('CN_STRAY_MARK_GUARD') == '0':
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True


def uninstall():
    if not _orig:
        return
    import correction_entry
    correction_entry.correct_line = _orig.pop('correct_line')
