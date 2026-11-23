# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""辞書の名詞2つ（どちらも2字以上の漢字・片仮名の語）の継ぎ目に「続けて置けない」として付いた紫を外す。

なぜ
----
名詞と名詞をつないだ複合語（会社名＋株式会社・時代＋末期）は日本語で自由に作れる形で、隣り合いの表に無くても
打ち違いの証にはならない（2026-11-22 うに「正しい文の紫の基準を見直す」・Fable 5.2 の方針: 弱い根拠の紫）。
打ち違いの跡の継ぎ目は、1字の漢字の切れ端（寺｜木｜升）か、辞書に無いかなの並び（ゅえはょの｜金額）になる。
2026-11-22 補正担当の数え: 692行の束と正しい文6000行の「続けて置けない」の紫で、両側が辞書の2字以上の名詞の組は
正しい文に2つ（明治｜末期 ほか）・誤字の当たりに0。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。紫の所に掛かる訳が全部
「続けて置けない」で、その2つの語が上の形のときだけ、その紫と訳を外す。字は変えない。
切り替え: CN_NOUN_COMPOUND_PURPLE=0 で前のまま。特定の語や文字列には合わせない。
"""
import functools
import os
import re

_orig = {}
_ADJ = re.compile('「(.+?)」と「(.+?)」は続けて置けない')


def _word(t):
    face = t.surface or ''
    if t.pos != '名詞' or not getattr(t, 'has_reading', False) or len(face) < 2:
        return False
    if str(t.pos_sub or '').startswith(('接尾', '数', '代名詞', '非自立')):
        return False
    return all('一' <= c <= '鿿' or c == '々' or 'ァ' <= c <= 'ヶ' or c == 'ー' for c in face)


def _compound_pair(toks, left, right):
    """left の語と right の語が隣り合って在り、どちらも辞書の2字以上の名詞か"""
    return any(p.surface == left and q.surface == right and p.end == q.start and _word(p) and _word(q)
               for p, q in zip(toks, toks[1:]))


def _verb_continues(toks, k):
    """動詞 toks[k] の形が、すぐ後ろの語へ普通につながるか（未然 → 助動詞、未然ヌ接続 → ぬ・ん、連用タ接続 → て・た）"""
    q = toks[k]
    r = toks[k + 1] if k + 1 < len(toks) else None
    form = str(getattr(q, 'infl_form', '') or '')
    if form.startswith('未然ヌ接続'):
        return r is not None and r.surface in ('ぬ', 'ん')
    if form.startswith('未然'):
        return r is not None and r.pos == '助動詞'
    if form.startswith('連用タ接続'):
        return r is not None and r.surface[:1] in ('て', 'た', 'で', 'だ')
    return True


def _object_drop(toks, left, right):
    """名詞と動詞の間の を・が を省いた話し言葉（顔しないで・話聞いてた・口紅してる）か。名詞は辞書の一般の名詞
    （接尾・固有名詞・数・代名詞でない）、動詞は辞書の自立の動詞で、その形が後ろへ普通につながる時だけ。
    打ち違いの跡（手せ価値・汗せし）は動詞の形が後ろへつながらない。CN_NOUN_VERB_PURPLE=0 で見ない"""
    if os.environ.get('CN_NOUN_VERB_PURPLE') == '0':
        return False
    for k in range(1, len(toks)):
        p, q = toks[k - 1], toks[k]
        if p.surface != left or q.surface != right or p.end != q.start:
            continue
        sub = str(p.pos_sub or '')
        # 名詞の前にもう を があれば、を を省いた形ではない（書類を手する は打ち違いの跡）
        if k >= 2 and toks[k - 2].surface == 'を' and toks[k - 2].end == p.start:
            continue
        if (p.pos == '名詞' and getattr(p, 'has_reading', False) and sub in ('一般', 'サ変接続')
                and q.pos == '動詞' and str(q.pos_sub or '') == '自立' and getattr(q, 'has_reading', False)
                and _verb_continues(toks, k)):
            return True
    return False


def filter_result(line, result):
    if os.environ.get('CN_NOUN_COMPOUND_PURPLE') == '0' or not isinstance(result, dict):
        return result
    odd = result.get('odd_spans') or []
    reasons = result.get('odd_reasons') or []
    if not odd or not reasons:
        return result
    text = result.get('corrected') or line
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return result
    dropped = set()
    for o in odd:
        a, b = o[0], o[1]
        why = [r for r in reasons if len(r) >= 3 and r[0] < b and a < r[1]]
        if not why:
            continue
        ok = True
        for r in why:
            m = _ADJ.match(str(r[2]))
            if not m or not (_compound_pair(toks, m.group(1), m.group(2)) or _object_drop(toks, m.group(1), m.group(2))):
                ok = False
                break
        if ok:
            dropped.add((a, b))
            dropped.update((r[0], r[1]) for r in why)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = [o for o in odd if (o[0], o[1]) not in dropped]
    out['odd_reasons'] = [r for r in reasons if (r[0], r[1]) not in dropped]
    if out.get('unsure_spans'):
        out['unsure_spans'] = [o for o in out['unsure_spans'] if (o[0], o[1]) not in dropped]
    return out


def correct_line(line, store, *a, **k):
    r = _orig['correct_line'](line, store, *a, **k)
    if os.environ.get('CN_NOUN_COMPOUND_PURPLE') == '0' or not isinstance(line, str):
        return r
    try:
        return filter_result(line, r)
    except Exception:
        return r


def install():
    if _orig or os.environ.get('CN_NOUN_COMPOUND_PURPLE') == '0':
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
