# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""推し量りだけの直しの後に、その所かすぐ隣に紫が残るなら、直しを戻して紫だけにする（2026-11-14 補正担当・未解決タブ）。

なぜ
----
書き手が IME で選んだ漢字を、読みの手がかりなしに消す・別の語にする直し（作った例: 差釣れません → 差れません、
誤変換の佑 → 多角）は推し量り。直した後もその辺りに紫が残るなら、直しが当たっていない見込みが高い。
誤った直しより紫のほうがよい（全体評価の方針）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
1. 直しの details がどれも推し量り（理由が 常用外の字・脱字、または漢字を含む所を消しただけの直し）か見る。
2. 直した所（元の行の位置）に重なるか隣り合う紫、または同じひらがなの続きの中の紫が在れば、行を元に戻し、直した所を紫にする（ほかの紫はそのまま）。
特定の語や文字列には合わせない。切り替え: CN_GUESS_BACK=0 で前のまま。
"""
import difflib
import functools
import os

GUESS_REASON = ('常用外の字',)
REASON = '打ち違いの見込みはあるが、直し先を決められない'
_orig = {}


def _on():
    return os.environ.get('CN_GUESS_BACK') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _guess(d):
    if not isinstance(d, (list, tuple)) or len(d) < 2:
        return False
    src, face = d[0], d[1]
    why = d[2] if len(d) > 2 else ''
    if why in GUESS_REASON or (isinstance(why, str) and why.startswith('脱字')):
        return True          # 脱字の足し（なであり → なでてあり）も、読みの手がかりの無い推し量り
    return isinstance(src, str) and face == '' and any(_kanji(c) for c in src)


def _same_kana_run(line, m, o):
    """2つの所が、元の行の同じひらがなの続き（全て｜ひらがなであり の ひらがなであり）の中に在るか。
    かなの続きの切り方が崩れると、紫と直しが同じ続きの中で離れて付く。"""
    hira = lambda c: 'ぁ' <= c <= 'ゖ' or c == 'ー'
    lo, hi = min(m[0], o[0]), max(m[1], o[1])
    lo, hi = max(lo, 0), min(hi, len(line))
    return hi > lo and all(hira(c) for c in line[lo:hi])


def back(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected') or line
    det = result.get('details') or ()
    if text == line:
        return _drop_stale(result)
    if not det or not all(_guess(d) for d in det):
        return result
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    if not odd:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
    marks = [(o[1], max(o[2], o[1] + 1)) for o in ops]
    if not any(a <= y and x <= b or _same_kana_run(line, (a, b), (x, y)) for a, b in marks for x, y in odd):
        return result
    # 直しを戻したので、直した後の不自然さの紫（fixed_still_odd）は当たらない
    try:
        import fixed_still_odd as _fso
        stale = _fso.REASON
    except Exception:
        stale = None
    keep_r = [r for r in result.get('odd_reasons') or () if not (len(r) > 2 and r[2] == stale)]
    gone = {tuple(r[:2]) for r in result.get('odd_reasons') or () if len(r) > 2 and r[2] == stale} \
        - {tuple(r[:2]) for r in keep_r}
    odd = [x for x in odd if x not in gone]
    out = dict(result)
    spans = sorted(set(odd) | set(marks))
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': [],
                'odd_spans': spans,
                'odd_reasons': keep_r + [(a, b, REASON) for a, b in marks]})
    return out


def _drop_stale(result):
    """書き換えの無い答えに残る「直した後も不自然」の紫（fixed_still_odd）は、指す直しが戻されて無いので外す
    （2026-11-14 未解決タブの正しい文: 外側の段が直しを戻した後に紫だけ残った）。既定はオフ"""
    # 既定はオフ（CN_GUESS_BACK_STALE=1 で入る）: 692行の打ち違いで、直しが戻された後のこの紫だけが残りの誤り
    # （離れた所の打ち違い）の印だった行が紫を失った（2026-11-14）
    # 書き換えの無い答えに直しの控え（details）だけが残る行は、直しが外側の段で戻された跡がはっきりしているので、既定で外す
    # （作った例: 型番の英字の直しを戻した後に「直した後も…」の紫だけが残った）。CN_GUESS_BACK_STALE_DET=0 で前のまま
    det_left = bool(result.get('details')) and os.environ.get('CN_GUESS_BACK_STALE_DET') != '0'
    if (os.environ.get('CN_GUESS_BACK_STALE') != '1' and not det_left) or not result.get('odd_spans'):
        return result
    try:
        import fixed_still_odd as _fso
        stale = _fso.REASON
    except Exception:
        return result
    reasons = result.get('odd_reasons') or ()
    gone = {tuple(r[:2]) for r in reasons if len(r) > 2 and r[2] == stale}
    if not gone:
        return result
    other = {tuple(r[:2]) for r in reasons if not (len(r) > 2 and r[2] == stale)}
    gone -= other
    if not gone:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if tuple(x[:2]) not in gone]
    out['odd_reasons'] = [r for r in reasons if tuple(r[:2]) not in gone]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        return back(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
