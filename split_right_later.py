# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""分割の表示でタブを切り替えた時、右の補正欄は後から描く（2026-11-21 09:56Z うにさん「描く順は、右の補正欄は遅れて
よい。品詞ごとのフォントは遅らせない」）。

切り替えの中で補正欄を作り直す（_render_corrected）と、左のメモ欄が描かれて打てるようになるのは、右の作り直し・
行そろえが済んだ後だった（3,000行のタブで 360〜410ms）。切り替えの時だけ、右の作り直しを次の一瞬へ回す:
・左のメモ欄（字・品詞ごとのフォント・空白の印）は今まで通りその場で描く
・右は after(1) で作り直す。その時にキー・クリックが Windows の列で待っていれば、先に通して少し後に（最長 MAX_WAIT_S）
・右を待っている間の行そろえは測らない（右がまだ前のタブの字なので、測っても捨てるだけ）。右を作り直した時に
  いつもの道（_render_corrected → _paint_whitespace → _align_pane_rows）で1回そろえる＝済んだ後の形は前と同じ
・待っている間に、ほかの道（解析の答え・打鍵）で補正欄を作り直したら、その作り直しが右を描くので予約は取り消す
品詞ごとのフォントは、左はその場で・右は補正欄の字と同じ作り直しで付く（字だけが先に出ることは無い）。
・右を待つ間は、前のタブの字を見せない（10:34Z「待つ間は右を空に。色や背景はそのまま、行番号も空に」）: 補正欄と
  その行番号の上に、それぞれの地の色の無地の板を重ねる（字を消して組み直すより軽い）。作り直した時に外す。
  CN_SPLIT_RIGHT_BLANK=0 で板を重ねない（前のタブの字が一瞬見える）
CN_SPLIT_RIGHT_LATER=0 で前の形（切り替えの中で右も作り直す）
"""
import os
import sys
import time

MAX_WAIT_S = 1.0
RETRY_MS = 30


def on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_SPLIT_RIGHT_LATER') != '0'


def input_waiting():
    """キー・マウスのボタンの知らせが Windows の列で待っているか（Tk がまだ取り出していない分）。"""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        QS_KEY, QS_MOUSEBUTTON = 0x0001, 0x0004
        return bool((int(ctypes.windll.user32.GetQueueStatus(QS_KEY | QS_MOUSEBUTTON)) >> 16) & (QS_KEY | QS_MOUSEBUTTON))
    except Exception:
        return False


def arm(app):
    """タブの切り替えの中で呼ぶ: この後の1回の補正欄の作り直しを後へ回す。"""
    try:
        if on() and not app._layout_is_unified():
            app._right_later_arm = True
    except Exception:
        pass


def disarm(app):
    app._right_later_arm = False


def blank_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_SPLIT_RIGHT_BLANK') != '0'


def _covers(app):
    got = getattr(app, '_right_later_covers', None)
    if got is not None:
        return got
    got = []
    import tkinter as tk
    for name in ('result_view', 'result_gutter'):
        w = getattr(app, name, None)
        if w is None:
            continue
        try:
            got.append((w, tk.Frame(w.master, bd=0, highlightthickness=0, takefocus=0)))
        except Exception:
            pass
    app._right_later_covers = got
    return got


def cover(app):
    if not blank_on():
        return
    for w, board in _covers(app):
        try:
            board.configure(bg=str(w.cget('bg')))
            board.place(in_=w, x=0, y=0, relwidth=1, relheight=1)
            board.lift(w)
        except Exception:
            pass


def uncover(app):
    for _w, board in getattr(app, '_right_later_covers', None) or ():
        try:
            board.place_forget()
        except Exception:
            pass


def pending(app):
    return getattr(app, '_right_later_job', None) is not None


def take(app):
    """_render_corrected の頭で呼ぶ。今は描かずに後へ回すなら True。後へ回していた分を別の作り直しが追い越す時は、
    予約を取り消して False（その作り直しが右を描く）。"""
    if getattr(app, '_right_later_arm', False):
        app._right_later_arm = False
        if not pending(app):
            app._right_later_since = time.monotonic()
            try:
                app._right_later_job = app.root.after(1, lambda: _run(app))
            except Exception:
                app._right_later_job = None
                return False
            cover(app)
        return True
    cancel(app)
    return False


def cancel(app):
    job = getattr(app, '_right_later_job', None)
    app._right_later_job = None
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass
        uncover(app)        # これから作り直す（呼んだ側がこのまま右を描く）


def _run(app):
    app._right_later_job = None
    if getattr(app, '_closing', False):
        return
    since = getattr(app, '_right_later_since', None) or time.monotonic()
    if input_waiting() and time.monotonic() - since < MAX_WAIT_S:
        try:                    # 打った字・押したボタンを先に通す
            app._right_later_job = app.root.after(RETRY_MS, lambda: _run(app))
            return
        except Exception:
            app._right_later_job = None
    # 補正欄の品詞のフォントも、描いて表示の位置を合わせてから見えている行に1回だけ塗る（左と同じ・CN_TAB_PAINT_AFTER_VIEW。
    # 前は字を入れた所で1行目あたりを塗り、位置を合わせた所でまた塗っていた）
    import os
    hold = (getattr(getattr(app, 'result_view', None), '_correctnote_boundary_colors', None)
            if os.environ.get('CN_TAB_PAINT_AFTER_VIEW') != '0' else None)
    if hold is not None:
        hold.hold_visible = time.monotonic() + 1.0
    try:
        app._render_corrected()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        if hold is not None:
            hold.hold_visible = 0.0
            if os.environ.get('CN_RIGHT_PAINT_AFTER_SYNC') != '0':
                # 補正欄の表示の位置を、メモ欄の今の位置へ先に合わせてから塗る（2026-11-23: 描いた直後の補正欄はまだ1行目に
                # いて、ここで1行目あたりの行を塗ってから位置を合わせていた・tests_tab_paint_after_view の right_far_above）。
                # CN_RIGHT_PAINT_AFTER_SYNC=0 で前の形
                try:
                    if not app._layout_is_unified():
                        app._sync_partner_to_line(app.editor, app.result_view)
                except Exception:
                    pass
            try:
                hold._paint_visible_now()
            except Exception:
                pass
        uncover(app)
