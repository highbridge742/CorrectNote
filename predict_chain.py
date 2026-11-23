# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""予測を選んで字が入ったら、入った後ろの位置で次の予測を続けて出す（2026-11-21 09:58Z うにさん「予測を選択して文字を
入れたら、次の予測を続けて出す」）。

F5 の予測の窓・行末の自動の候補・行頭の予測のどれでも、選んだ字を入れた（app._f5_predict_insert）後、
・次の一瞬（after_idle）に、カーソルが入れた後ろのまま・焦点がその欄のままなら、同じ形で予測を開く
  （F5 で開いた形なら1つ目を選んだ形・自動の形なら焦点を取らない形。置き場はいつもの道＝マウスの近く・補正欄を隠さない）
・その間に別のキーを押した・クリックした（カーソルが動いた）・焦点が外れた・ほかの一覧が出ている時は出さない
・スクロールの後の止め（auto_candidates の scroll hold）が立っていれば出さない
・予測が無ければ出さない（_f5_predict_open が False）
・続けて出した一覧は、離す前に押していないクリック（選んだダブルクリックの2回目など）では決めない
出した一覧は Esc・ほかのキーでいつも通り閉じる＝そこで止まる。行頭の予測は入れた後に右に字が残るので、続けて出す時だけ
「右に字が無い所・行頭」の決まりを外す（候補は左の字から出す）。CN_PREDICT_CHAIN=0 で前の形
"""
import os
import time


def on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_PREDICT_CHAIN') != '0'


def cancel(app):
    job = getattr(app, '_predict_chain_job', None)
    app._predict_chain_job = None
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass


def after_insert(app, widget, owner, kind):
    """予測の字を入れた直後に呼ぶ。kind: 開いた時の形（None＝F5・'line_end' など＝焦点を取らない自動の形）。"""
    if not on():
        return
    cancel(app)
    try:
        expected = str(widget.index('insert'))
        app._predict_chain_job = app.root.after_idle(lambda: _open(app, widget, owner, kind, expected))
    except Exception:
        app._predict_chain_job = None


def _open(app, widget, owner, kind, expected):
    app._predict_chain_job = None
    if getattr(app, '_closing', False):
        return False
    try:
        if not int(widget.winfo_exists()):
            return False
        if app.root.focus_get() is not widget:
            return False                                   # 焦点が外れた
        if str(widget.index('insert')) != expected:
            return False                                   # 別のキー・クリックでカーソルが動いた
    except Exception:
        return False
    if getattr(app, '_dropdown', None) is not None:
        return False                                       # ほかの一覧が出ている
    if os.environ.get('CN_PREDICT_CHAIN_RIGHT_EMPTY') != '0':
        # 入れた後にカーソルの右に字がある時は出さない（行頭・途中どちらも。2026-11-22 01:56Z うにさん「右に文字がるところで
        # 行頭でF5から「・」をいれたら、次に予測候補が出た。右に文字があるときは出さない」）。CN_PREDICT_CHAIN_RIGHT_EMPTY=0 で
        # 前の形（行頭の予測を入れた後は右に字が残っても出す）
        try:
            if widget.get('insert', 'insert lineend') != '':
                return False
        except Exception:
            return False
    if getattr(app, '_auto_scroll_hold', False) and os.environ.get('CN_AUTO_SCROLL_HOLD') != '0':
        return False                                       # スクロールの後（クリックかキーで動かすまで出さない）
    try:
        import auto_candidates as _AC
        if _AC.jump_held(app):
            return False                                   # 飛んだ移動の後（14:13Z・CN_AUTO_SKIP_JUMPS）
    except Exception:
        pass
    try:
        import sys
        mod = sys.modules.get(type(app).__module__)
        pos = getattr(mod, '_python_text_position')
        row, col = pos(widget, widget.index('insert'))
    except Exception:
        return False
    if kind is None and owner == 'main' and os.environ.get('CN_PREDICT_CHAIN_NO_FOCUS') != '0':
        # 続けて出す一覧は、F5 で開いた後でも焦点を取らず、候補も選んでいない形（自動の形と同じ）で出す（2026-11-21 14:36Z
        # うにさん「予測決定後に出す予測は、候補がフォーカスしていない状態にする」）。打鍵は本文へ・Enter は改行・下キーや
        # クリックで選ぶ。CN_PREDICT_CHAIN_NO_FOCUS=0 で前の形（F5 の形なら1つ目を選んだ形）
        kind = 'line_end'
    app._predict_chain_opening = True
    app._dropdown_passive = kind
    try:
        opened = bool(app._f5_predict_open(widget, row, col, owner))
    except Exception:
        opened = False
    finally:
        app._predict_chain_opening = False
        app._dropdown_passive = None
    if opened and kind:
        try:
            import auto_candidates as AC
            shown = AC.passive(app)
            if shown is not None:
                shown['where'] = AC._where(widget)         # 行末の自動の候補が同じ所へ出し直さない
        except Exception:
            pass
    app._predict_chain_opened_at = time.monotonic() if opened else None
    return opened
