# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""人が確定した「はかる」の漢字（測・計・量）を、同じ族の別の字に書き換えない
（2026-11-23 補正担当、うに 誤判定タブ: 時間の長さを 測って と書いた行が 計って に書き換わった）。

なぜ
----
測る・計る・量る は、どれも値を確かめる意味で、使い分けは書き手の好みの幅が広い。対象の名詞から1つに決める直しは、
人が選んで打った正しい字を書き換えてしまう（間違った書き換えは紫より悪い）。族の外の字（図る など）からの直しは残す。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
答えの直しがどれも「測・計・量 の1字を同じ族の別の1字に替えただけ」なら、元の行に戻し、その所の紫と理由も外す。
直しがほかにも在る行は見ない（そのまま）。切り替え: CN_MEASURE_KEEP=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}
FAMILY = frozenset('測計量')


def _on():
    return os.environ.get('CN_MEASURE_KEEP') != '0'


def keep(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    done = result.get('corrected')
    if not isinstance(done, str) or done == line or len(done) != len(line):
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return result
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'replace' or i2 - i1 != 1 or j2 - j1 != 1:
            return result
        if line[i1] not in FAMILY or done[j1] not in FAMILY:
            return result
        # 送り仮名の「る・っ・り・れ・ら・ろ」が続く動詞の所だけ（計量・測量 のような語の中の字は見ない）
        if i2 >= len(line) or line[i2] not in 'るっりれらろ':
            return result
    spots = [(o[1], o[2]) for o in ops]

    # 「直した後も…」の紫は直しの在る行にだけ付く。直しを戻した行には付かないので、その理由だけの紫も外す
    # （2026-11-23 補正担当: 戻した後、離れた所に「直した後も…」の紫だけが残った）
    try:
        import fixed_still_odd as F
        why = F.REASON
    except Exception:
        why = None
    reasons = result.get('odd_reasons') or ()
    only_fso = {tuple(r[:2]) for r in reasons if len(r) > 2 and r[2] == why}
    only_fso -= {tuple(r[:2]) for r in reasons if len(r) > 2 and r[2] != why}

    def near(x):
        return tuple(x[:2]) in only_fso or any(x[0] <= b + 1 and a <= x[1] + 1 for a, b in spots)

    out = dict(result)
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': [],
                'odd_spans': [x for x in result.get('odd_spans') or () if not near(x)],
                'odd_reasons': [r for r in result.get('odd_reasons') or () if not near(r)]})
    out.pop('unsure_spans', None)
    return out


def correct_line(line, store=None, *args, **kwargs):
    result = _orig['correct_line'](line, store, *args, **kwargs)
    try:
        return keep(line, result)
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
