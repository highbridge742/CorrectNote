# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""F5（語の候補）を、解析の子を本体で待たずに開く（2026-11-23・決まり「マウス・キーから呼ばれる本体の処理は解析の子を
同期で待たない」）。前は、解析の途中に F5 を押すと、子が解いている行を取り消して候補の答えを本体で待ち、本体が約 0.3秒
止まっていた。

・子が本体の行を解いている間に押した F5 は、その場では何もせず、押した時の様子（欄・カーソル・選択・本文の変わり目・
  タブ・表示）と押した回数を覚える。押し直しは回数を足すだけ
・子が1行を解き終えた合間（app._nearby_words_for → run_waiting・子が空いている）に、押した回数だけ F5 の処理を
  やり直す。候補の答えは子へ待たない頼みで出し（auto_candidates._hover_ask と同じ作り）、答えがそろうまで解析の次の
  行は頼まない（hold・子は本体の行を捨てない）。答えがそろったら、はじめから押した回数だけやり直して一覧を開く
  （前の形で同じ押し方をした時と同じ候補・同じ選択位置）
・待ちの間に、ほかのキー・クリック・カーソルの移動・本文の変化・タブの切り替え・Esc があったら開かずにやめる。待ちは
  長くても TIMEOUT_S。子がいない・作り直された・解析の段取りが変わった時も外れる
・遡りの途中（一覧が開いている・F5 の印が残っている）の F5 は、今までどおりその場で動かす
CN_F5_ASYNC=0 で前の形。
"""
import os
import time

TIMEOUT_S = 6.0
POLL_MS = 15
_PASS_KEYS = ('F5', 'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R')


def on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_ASYNC') != '0'


def _fresh(app):
    """遡りの途中でない、まっさらな F5 か。"""
    return (getattr(app, '_dropdown', None) is None and not getattr(app, '_f2_cycle', None)
            and getattr(app, '_f2_focus_target', None) is None)


def _snapshot(app, widget):
    try:
        whole = getattr(widget, '_correctnote_whole_text', None) or {}
        return (widget, str(widget.index('insert')), tuple(str(i) for i in widget.tag_ranges('sel')),
                whole.get('changes'), getattr(getattr(app, 'session', None), 'active', None),
                str(widget.index('@0,0')))
    except Exception:
        return None


def _same(app, w):
    snap = w.get('snap')
    return snap is not None and _snapshot(app, snap[0]) == snap


def pending(app):
    return getattr(app, '_f5_wait', None) is not None


def cancel(app):
    w = getattr(app, '_f5_wait', None)
    app._f5_wait = None
    job = (w or {}).get('job')
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass


def defer(app, event):
    """F5 を押した: 今は開かずに、子の合間に開く（True）。今までどおりその場で開くなら False。"""
    if not on():
        return False
    w = getattr(app, '_f5_wait', None)
    if w is not None:
        if _same(app, w):
            w['presses'] += 1            # 押し直し: 開く時に同じ数だけ送る
            return True
        cancel(app)
        return False
    import auto_candidates as AC
    if not AC.gap_async_on() or not AC.worker_in_use(app) or not _fresh(app):
        return False
    widget = getattr(event, 'widget', None)
    if widget not in (getattr(app, 'editor', None), getattr(app, 'result_view', None)):
        try:
            widget = app.root.focus_get()
        except Exception:
            widget = None
        if widget not in (getattr(app, 'editor', None), getattr(app, 'result_view', None)):
            return False
    try:
        if not widget.tag_ranges('sel'):
            if not widget.get('insert', 'insert lineend').strip():
                return False             # カーソルの右に字が無い: 予測で開く（子に尋ねない）ので、その場で
            left = widget.get('insert linestart', 'insert')
            if not left.strip():
                return False             # 行頭: 予測で開く（右に字があっても・f5_predict）
            import f5_predict
            if f5_predict.after_head(app, left, f5_predict.has_wide(left)):
                return False             # 行頭の候補を入れた後: これも予測
    except Exception:
        return False
    snap = _snapshot(app, widget)
    if snap is None:
        return False
    app._f5_wait = dict(snap=snap, presses=1, since=time.monotonic(), event=event, asks=None, job=None)
    if _preempt(app):
        # 人が今押した F5 を先に: 子が解いている本体の行を取り消し、本体で待たずに F5 の頼みを出す。取り消した行は
        # 解析が次に進む時に頼み直す（行の答えをまだ当てていないので、line_step がその行をもう一度頼む）。F5 の答えを
        # 待つ間は解析の次の行を頼まない（hold）が、答え・待ちの外れのどちらでも待ちは外れる
        if _attempt(app, app._f5_wait) == 'busy':
            app._f5_wait['asks'] = None       # 頼めなかった: 子の合間に開く（run_waiting）
    return True


def _preempt_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_ASYNC_PREEMPT') != '0'


def _preempt(app):
    """子が解いている本体の行（解析の頼み）を取り消せたら True（前の同期の形 analysis_async.ask_child と同じ取り消し）。
    裏のタブの行が同じ子を使っている時（メモリ「中」）・取り消さない種類の頼みの時は False（子の合間を待つ）。"""
    if not _preempt_on():
        return False
    import analysis_async
    pending = getattr(app, '_async_request', None)
    if pending is None:
        return False
    try:
        kind = pending[0][0]
    except (TypeError, IndexError):
        return False
    if kind not in ('line', 'prepare', 'plans'):
        return False
    if getattr(app, '_async_background_request', None) is not None:
        try:
            import memory_usage
            if memory_usage.shares_worker(app):
                return False
        except Exception:
            return False
    try:
        analysis_async.cancel_foreground_request(app)
        if kind == 'prepare':
            # 下準備を取り消した: ask_child と同じく、少し後に解析をやり直す
            app._async_context_scope = None
            app.root.after(analysis_async.PREPARE_POLL_MS, app._analyze_if_changed)
    except Exception:
        return False
    w = getattr(app, '_f5_wait', None)
    if w is not None:
        w['preempted'] = pending[0]
    return True


def defer_quick(app, event):
    """簡易入力の F2 も、本体の F5 と同じく待たずに開く（2026-11-23・CN_QUICK_F2_ASYNC=0 で前の形）。"""
    if not on() or os.environ.get('CN_QUICK_F2_ASYNC') == '0':
        return False
    tw = getattr(app, '_quick_text', None)
    if tw is None:
        return False
    w = getattr(app, '_f5_wait', None)
    if w is not None:
        if w.get('quick') and _same(app, w):
            w['presses'] += 1
            return True
        cancel(app)
        return False
    import auto_candidates as AC
    if (not AC.gap_async_on() or not AC.worker_in_use(app) or getattr(app, '_dropdown', None) is not None
            or getattr(app, '_f2q_cycle', None)):
        return False
    try:
        if not tw.tag_ranges('sel'):
            if not tw.get('insert', 'insert lineend').strip():
                return False             # 予測で開く（子に尋ねない）
            left = tw.get('insert linestart', 'insert')
            if not left.strip():
                return False
            import f5_predict
            if f5_predict.after_head(app, left, f5_predict.has_wide(left)):
                return False
    except Exception:
        return False
    snap = _snapshot(app, tw)
    if snap is None:
        return False

    def reset():
        try:
            app._close_dropdown()
        except Exception:
            pass
        app._f2q_cycle = None
        try:
            tw.tag_remove('f2_focus', '1.0', 'end')
            tw.tag_remove('f2_next', '1.0', 'end')
        except Exception:
            pass
        try:
            app._clear_f2_target()
        except Exception:
            pass
    app._f5_wait = dict(snap=snap, presses=1, since=time.monotonic(), event=None, asks=None, job=None, quick=True,
                        replay=lambda: app._on_quick_f2_open(None), reset=reset)
    if _preempt(app):
        if _attempt(app, app._f5_wait) == 'busy':
            app._f5_wait['asks'] = None
    return True


def defer_action(app, widget, action):
    """右クリックの候補（_open_editor_dropdown / _open_dropdown）も、F5 と同じく本体で待たずに開く（2026-11-23）。
    action は一覧を開く関数（答えが足りなければ子へ待たない頼みを出し、そろってから呼び直す）。今までどおり
    その場で開くなら False。CN_RIGHT_CLICK_ASYNC=0 で前の形"""
    if not on() or os.environ.get('CN_RIGHT_CLICK_ASYNC') == '0':
        return False
    import auto_candidates as AC
    if getattr(app, '_f5_wait', None) is not None:
        cancel(app)                      # 前に押した F5・右クリックは、新しい右クリックでやめる
    if not AC.gap_async_on() or not AC.worker_in_use(app):
        return False
    snap = _snapshot(app, widget)
    if snap is None:
        return False
    app._f5_wait = dict(snap=snap, presses=1, since=time.monotonic(), event=None, asks=None, job=None, action=action)
    if _preempt(app):
        if _attempt(app, app._f5_wait) == 'busy':
            app._f5_wait['asks'] = None
    return True


def note_input(app, event):
    """待ちの間のほかのキー・クリック: 開かずにやめる。"""
    if getattr(app, '_f5_wait', None) is None:
        return None
    keysym = getattr(event, 'keysym', None)
    if keysym in _PASS_KEYS:
        return None
    cancel(app)
    return None


def _expired(app, w):
    return time.monotonic() - w.get('since', 0.0) > TIMEOUT_S or not _same(app, w)


def run_waiting(app):
    """子が1行を解き終えた合間（_analyze_slice の中・子は空いている）: 待っている F5 を開く。
    子に頼みを出したら auto_candidates.HoldAnalysis を上げて、この回は次の行を頼ませない。"""
    w = getattr(app, '_f5_wait', None)
    if w is None or w.get('asks') is not None or not getattr(app, '_cn_in_analyze_slice', False):
        return False
    if getattr(app, '_async_request', None) is not None:
        return False
    if _expired(app, w):
        cancel(app)
        return False
    import auto_candidates as AC
    if _attempt(app, w) == 'deferred':
        raise AC.HoldAnalysis()
    return True


def hold(app):
    """F5 の頼みの答えを待つ間は、解析の次の行を頼まない（auto_candidates.hold_analysis と同じ外し方）。"""
    w = getattr(app, '_f5_wait', None)
    asks = (w or {}).get('asks')
    if not on() or not asks or not asks.get('pending'):
        return False
    if _expired(app, w):
        cancel(app)
        return False
    if getattr(app, '_async_request', None) is not None:
        return False
    worker = asks.get('worker')
    if worker is not None:
        try:
            if (worker is not getattr(app, '_correction_worker', None) or getattr(worker, 'closed', False)
                    or not worker.process.is_alive()):
                cancel(app)
                return False
        except Exception:
            cancel(app)
            return False
    if 'work' in asks and asks.get('work') != getattr(app, '_analyze_work', None):
        cancel(app)
        return False
    return True


def _reset(app):
    """やり直す前に、まっさらな F5 の前の姿へ（押した時は一覧も印も無かった）。"""
    w = getattr(app, '_f5_wait', None)
    if w is not None and w.get('reset') is not None:
        w['reset']()
        return
    try:
        app._close_dropdown()
    except Exception:
        pass
    try:
        app._clear_f2_target()
    except Exception:
        pass
    app._f2_cycle = None


def _attempt(app, w):
    """押した回数だけ F5 をやり直す。答えが足りなければ頼みを出して 'deferred'、開けたら 'done'、やめたら 'gone'。"""
    import analysis_async
    import auto_candidates as AC
    if w.get('asks') is None:
        w['asks'] = dict(key='f5', pending={}, got={}, done=w.pop('done_cache', None) or {}, since=time.monotonic())
    asks = w['asks']
    _reset(app)
    real_ask = analysis_async.ask_child
    analysis_async.ask_child = AC._hover_ask(app, store=lambda a: a._f5_wait['asks'])
    outcome = 'done'
    try:
        if w.get('action') is not None:
            w['action']()                # 右クリック: 一覧を開く関数をそのまま
        elif w.get('replay') is not None:
            for _ in range(int(w.get('presses', 1))):
                w['replay']()            # 簡易入力の F2: 押した回数だけ
        else:
            for _ in range(int(w.get('presses', 1))):
                app._on_f2_candidates_open(w.get('event'))
    except AC._Deferred:
        outcome = 'deferred'
    except AC._Busy:
        outcome = 'busy'
    except AC._GiveUp:
        outcome = 'gone'
    except Exception:
        outcome = 'gone'
    finally:
        analysis_async.ask_child = real_ask
    if outcome == 'deferred':
        _reset(app)                      # 途中まで付けた印は外して待つ（開く時にはじめからやり直す）
        asks['since'] = time.monotonic()
        try:
            w['job'] = app.root.after(POLL_MS, lambda: _poll(app))
        except Exception:
            cancel(app)
            return 'gone'
        return 'deferred'
    if outcome == 'busy':
        _reset(app)
        w['done_cache'] = asks.get('done')
        w['asks'] = None                 # 子が本体の行を解いている: 次の合間にやり直す（届いた答えは使い回す）
        return 'busy'
    app._f5_wait = None
    if outcome == 'done':
        try:
            import reinput
            reinput.hide_cursor_for_reconvert(app)
        except Exception:
            pass
    return outcome


def _poll(app):
    w = getattr(app, '_f5_wait', None)
    if w is None:
        return
    w['job'] = None
    if _expired(app, w):
        cancel(app)
        return
    asks = w.get('asks') or {}
    worker = getattr(app, '_correction_worker', None)
    try:
        import auto_candidates as AC
        if worker is not None and asks.get('pending'):
            AC._drain(worker)
            for k, rid in list(asks['pending'].items()):
                got = worker.ready.pop(rid, None)
                if got is not None:
                    asks['got'][k] = got
                    asks['pending'].pop(k, None)
    except Exception:
        cancel(app)
        return
    if asks.get('pending'):
        try:
            w['job'] = app.root.after(POLL_MS, lambda: _poll(app))
        except Exception:
            cancel(app)
        return
    _attempt(app, w)                     # そろった: はじめから押した回数だけやり直して開く
