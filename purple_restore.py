# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""かなの並びの紫を、格子が語を置いて外したのに、後の段が置いた語を全部戻して行が打ったかなのままになったら、外した紫を
付け直す。

なぜ
----
kana_lattice_place._place_over_purple は「品詞として識別できない」かなの並びに語を置けると、その並びの紫を外す。後の段
（_unexplained_change_guard・kana_keep など）が置いた語を戻すと、行は打ったかなのままで紫も無くなり、打ち違いの行を
紫なしで見逃していた（2026-11-21 補正担当: 作り例のかなだけの行 1948 行の試し）。

どうやって
----------
既存のファイルは変えない（kana_lattice_place が外した紫を _CLEARED に残すだけ）。install() が correction_entry.correct_line
を外から包み、答えが打った行と同じで紫が無く、その行の外した紫が残っていれば、その紫と訳を戻す。
切り替え: CN_PURPLE_RESTORE=0 で前のまま。
"""
import functools
import os

_orig = {}


def correct_line(line, *a, **k):
    f = _orig['correct_line']
    if os.environ.get('CN_PURPLE_RESTORE') == '0' or not isinstance(line, str):
        return f(line, *a, **k)
    try:
        import kana_lattice_place as K
    except Exception:
        return f(line, *a, **k)
    saved = K._CLEARED
    K._CLEARED = {}
    try:
        r = f(line, *a, **k)
        got = K._CLEARED.get(line)
    finally:
        K._CLEARED = saved
    if not isinstance(r, dict) or not got:
        return r
    if (r.get('corrected') or line) != line or r.get('odd_spans'):
        return r
    spans, reasons = got
    if not spans:
        return r
    out = dict(r)
    out['odd_spans'] = [tuple(x) for x in spans]
    out['odd_reasons'] = [tuple(x) for x in reasons] if reasons else [tuple(x) + ('品詞として識別できない（かなの並びに説明が付かない）',) for x in spans]
    return out


def install():
    if _orig or os.environ.get('CN_PURPLE_RESTORE') == '0':
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
