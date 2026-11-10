# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""読み直しの候補を、補正に通す前に軽い見積もりで絞る（2026-11-10・全体評価 B2・うにさん「進めて」）。

なぜ
----
last_keystroke の読み直し（retry）は、戻した候補の行を1つずつ補正の入口（corrector.correct_line）に通す。
通し1回は 1〜3秒。作った誤字の束 90行では、この道の通し 410回のうち、最後の答えに採られたのは 1回だった。
採られた候補は、通す前の行の並びの費用（morphology.path_cost・数ミリ秒）が元の行より大きく下がっていた
（束で採られた 28候補はどれも 5,400 以上）。下がりの小さい候補は、通しても採られない。

どうやって
----------
corrector.correct_line を外から包み、「読み直しの中から直に呼ばれた通し」（last_keystroke._ACTIVE と
contextual_repair.SLIP_REVERTED が立っている・親の通しは読み直しの外）だけを見る。
元の行（親の通しの行）の費用 − 候補の行の費用 が MIN_GAIN に届かなければ、通さずに None を返す。
retry の呼び手は None を「この候補は採らない」として次へ進む（前からの作り）。

決まり
------
- 既存のファイルは変えない。install() の間だけ包む。
- 読み直しの候補だけ。行そのものの通し・ほかの段の通しは変えない。費用が出ない行は通す（前のまま）。
- 特定の語や文字列には合わせない。

切り替え: CN_PASS_SCREEN=0 で前のまま。CN_PASS_SCREEN_GAIN=数 で線を変える（既定 MIN_GAIN）。
"""
import os
from contextvars import ContextVar

MIN_GAIN = 2000     # last_keystroke.CLAUSE_GAIN（読み直しを採る線）と同じ

_orig = {}
_STATE = ContextVar('correctnote_pass_screen', default=None)
STATS = {'candidates': 0, 'skipped': 0}


def _min_gain():
    v = os.environ.get('CN_PASS_SCREEN_GAIN')
    if v is not None:
        try:
            return int(v)
        except ValueError:
            pass
    return MIN_GAIN


def _cost(text):
    try:
        import morphology
        return morphology.path_cost(text)
    except Exception:
        return None


def correct_line(line, *args, **kwargs):
    fn = _orig['correct_line']
    try:
        import last_keystroke
        import contextual_repair
        active = bool(last_keystroke._ACTIVE.get()) and bool(contextual_repair.SLIP_REVERTED.get())
    except Exception:
        return fn(line, *args, **kwargs)
    parent = _STATE.get()
    if active and parent is not None and not parent['active'] and isinstance(line, str):
        STATS['candidates'] += 1
        if parent['cost'] is False:
            parent['cost'] = _cost(parent['line'])
        base = parent['cost']
        cost = _cost(line) if base is not None else None
        if base is not None and cost is not None and base - cost < _min_gain():
            STATS['skipped'] += 1
            return None
    token = _STATE.set({'line': line, 'active': active, 'cost': False})
    try:
        return fn(line, *args, **kwargs)
    finally:
        _STATE.reset(token)


def install():
    """包みを掛ける（もう掛かっていれば何もしない）。CN_PASS_SCREEN=0 なら掛けない。"""
    if _orig or os.environ.get('CN_PASS_SCREEN') == '0':
        return bool(_orig)
    import corrector
    _orig['correct_line'] = corrector.correct_line
    corrector.correct_line = correct_line
    return True


def uninstall():
    if not _orig:
        return
    import corrector
    corrector.correct_line = _orig.pop('correct_line')
