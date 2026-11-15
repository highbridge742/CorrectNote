# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""紫の所の読み直しを、時計（8秒）ではなく仕事の量（補正に通した回数）で切る（2026-11-10・試作）。

なぜ
----
correction_entry._deadline_run は、読み直しを始めてから ODD_RESPELL_SEC（8秒）を過ぎたら、その行は読み直さない。
時計で切るので、同じ行が PC の速さ・混み具合で「直る／紫だけ」に変わる。
補正に通した回数（corrector.correct_line を本当に通した回数）は、機械が違っても混んでいても同じ数になる。
通した回数と掛かった秒は強く比例する（作った誤字の束で相関 0.9）ので、回数で切れば、重い行を切る働きは
そのままで、答えが揺れなくなる。

どうやって
----------
correction_entry._deadline_run を外から置き換える。読み直し1回（_deadline_run の1回の呼び出し）の中で
corrector.correct_line を通した回数を数え、次の候補を通す前に PASS_BUDGET に届いていたら、前からと同じ
_RespellTimeout を投げる（その行は読み直さない＝前の答えのまま）。切る場所は前と同じ（候補と候補の間）。
時計の上限は、万一の守りとして長め（SAFETY_SEC）に残す。

決まり
------
- 既存のファイルは変えない。install() の間だけ置き換える。uninstall() で元に戻る。
- 特定の語や文字列には合わせない。

切り替え: CN_RESPELL_BUDGET=0 で前のまま（時計の8秒）。CN_RESPELL_BUDGET=数 で回数の線、
CN_RESPELL_SAFETY_SEC=秒 で守りの時計（0 で時計なし）。
"""
import os
import time

PASS_BUDGET = 12      # 読み直し1回の中で補正に通してよい回数（うに 2026-11-13 10:24Z「回数は増やしてもいいが抑えて」: 8→12）
SAFETY_SEC = 30.0     # 万一の守りの時計（ふつうは掛からない長さ）

_orig = {}
_COUNT = {'passes': 0}
STATS = {'runs': 0, 'cut_budget': 0, 'cut_clock': 0}


def _env_num(name, default, cast):
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return cast(v)
    except ValueError:
        return default


def _correct_line(*a, **k):
    _COUNT['passes'] += 1
    return _orig['correct_line'](*a, **k)


def _real_passes():
    """本当に通した回数。pass_screen がこの包みの内側に在ると、通さずに返した候補もここを通らないのでそのまま。
    外側に在る時（こちらが先に掛かった時）も、通さなかった候補はここまで来ないのでそのまま数えてよい。
    こちらが外側の時だけ、pass_screen が通さなかった数を引く。"""
    n = _COUNT['passes']
    try:
        import sys
        ps = sys.modules.get('pass_screen')
        if ps is not None and ps._orig and _orig.get('correct_line') is ps.correct_line:
            n -= ps.STATS['skipped']
    except Exception:
        pass
    return n


def _deadline_run(run, sec=None):
    budget = _env_num('CN_RESPELL_BUDGET', PASS_BUDGET, int)
    if budget <= 0:
        return _orig['_deadline_run'](run, sec)
    # 時間切れなしの比べ（CN_ODD_RESPELL_SEC=0）でも回数の線は働く。守りの時計だけ CN_RESPELL_SAFETY_SEC で
    safety = _env_num('CN_RESPELL_SAFETY_SEC', SAFETY_SEC, float)
    import correction_entry as ce
    start = _real_passes()
    end = time.monotonic() + safety if safety > 0 else None
    STATS['runs'] += 1

    def wrapped(*a, **k):
        if _real_passes() - start >= budget:
            STATS['cut_budget'] += 1
            raise ce._RespellTimeout()
        if end is not None and time.monotonic() > end:
            STATS['cut_clock'] += 1
            raise ce._RespellTimeout()
        return run(*a, **k)
    return wrapped


def install():
    """置き換える（もう掛かっていれば何もしない）。CN_RESPELL_BUDGET=0 なら掛けない。"""
    if _orig or os.environ.get('CN_RESPELL_BUDGET') == '0':
        return bool(_orig)
    import corrector
    import correction_entry as ce
    _orig['correct_line'] = corrector.correct_line
    _orig['_deadline_run'] = ce._deadline_run
    import functools
    functools.update_wrapper(_correct_line, _orig['correct_line'])   # 元の引数が外から見えるように（2026-11-13）
    corrector.correct_line = _correct_line
    ce._deadline_run = _deadline_run
    return True


def uninstall():
    if not _orig:
        return
    import corrector
    import correction_entry as ce
    if corrector.correct_line is _correct_line:
        corrector.correct_line = _orig['correct_line']
    ce._deadline_run = _orig['_deadline_run']
    _orig.clear()
