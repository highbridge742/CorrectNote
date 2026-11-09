# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""解析の途中で決まった紫を、答えを待たずに先に出す（2026-11-05 うにさん「紫だけ先に」）。

子は補正の1段目（correction_entry の最初の補正）が済んだ所で、その行の紫だけを送る（analysis_worker.early_*）。
本体はその行に仮の紫を塗る。直しは今までどおり答えの時刻に出し、答えが来たら仮の紫は外して答えの紫で描く。
仮の紫は別のタグ（同じ色）に塗るので、答えの描き方（ui_projection.update_tag の控え）には混ざらない。
行の文字が送った時と違っていれば塗らない。紫を下げる台帳（decisions）と「紫を出す」の設定は答えと同じに効かせる。"""
import os

TAG = 'odd_early'


def enabled():
    return os.environ.get('CN_EARLY_ODD') != '0'


def _tag(widget, like):
    if getattr(widget, '_correctnote_early_tag', False):
        return
    try:
        widget.tag_configure(TAG, background=widget.tag_cget(like, 'background'))
        try:
            widget.tag_raise(TAG, like)
            widget.tag_raise('sel', TAG)
        except Exception:
            pass
        widget._correctnote_early_tag = True
    except Exception:
        pass


def _paint(widget, like, row, payload, decisions, show):
    """row: 1から。payload: 子が送った {'line', 'odd'}。"""
    if not enabled() or widget is None or not show:
        return False
    line = payload.get('line')
    try:
        if widget.get(f'{row}.0', f'{row}.end') != line:
            return False
        import corrector
        spans = list(corrector.visible_odd_spans(line, payload.get('odd') or (), decisions))
        _tag(widget, like)
        widget.tag_remove(TAG, f'{row}.0', f'{row}.end')
        for start, end in spans:
            widget.tag_add(TAG, f'{row}.0+{start}c', f'{row}.0+{end}c')
        return bool(spans)
    except Exception:
        return False


def _clear(widget, row=None):
    if widget is None or not getattr(widget, '_correctnote_early_tag', False):
        return
    try:
        if row is None:
            widget.tag_remove(TAG, '1.0', 'end')
        else:
            widget.tag_remove(TAG, f'{row}.0', f'{row}.end')
    except Exception:
        pass


def memo(app, index, payload):
    """メモ欄の行（0から）。"""
    settings = getattr(app, 'settings', None)
    show = settings.get('show_odd') if settings is not None else True
    return _paint(getattr(app, 'editor', None), 'odd', index + 1, payload, getattr(app, 'decisions', None), show)


def clear_memo(app, index=None):
    _clear(getattr(app, 'editor', None), None if index is None else index + 1)


def quick(app, payload):
    """簡易入力の行（payload['row'] は0から）。

    簡易入力の欄は紫だけの所（直しの無い紫）を出さない（_finish_quick_analysis は suspect の単位だけ塗る）。
    途中の紫を塗ると、答えでは出ない印が一時見えるので塗らない（2026-11-06 実測: 紫だけの行で印が出て消えた）。
    簡易入力が紫を出すようになったら CN_EARLY_ODD_QUICK=1 で試せる。"""
    if os.environ.get('CN_EARLY_ODD_QUICK') != '1':
        return False
    row = payload.get('row')
    if row is None:
        return False
    return _paint(getattr(app, '_quick_text', None), 'suspect', row + 1, payload, getattr(app, 'decisions', None), True)


def clear_quick(app):
    _clear(getattr(app, '_quick_text', None))
