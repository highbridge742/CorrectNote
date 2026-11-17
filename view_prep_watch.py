# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""表示準備中の見張り（2026-11-17 うにさん「タブを移動したら表示準備中から一向に進まない」）。

控えから戻したタブは、表示の単位を本体の小分け（_analyze_chunk）で組む。小分けが続かなくなると「表示準備中」が消えない。
止まり方は2つ考えられた:
  A: _view_changing()（窓のドラッグ中・動かした直後）が立ったまま。小分けは「後で」を 30ms ごとに繰り返し、進まない
  B: 小分けの頭で入力の確かめの予約（_after_id）が残っていて、続きを予約せずに抜けた。確かめが来ない・来ても
     _tab_warming などで小分けを予約し直さないと、二度と続かない
見張りは表示準備中の間だけ 500ms ごとに見て、
  ・小分けの続きも確かめの予約も生きていない → 小分けを予約し直す
  ・窓のドラッグの印が 1.5 秒以上立ったまま、マウスのボタンは離れている → 印を下ろす
  ・10 秒進まない → 状態を1行記録する（本文は書かない）
記録は tools_local\\scroll_trace\\view_prep.log（大きな解き直しの記録と同じ扱い: 開発版は既定で取る・EXE は取らない）。
CN_VIEW_PREP_WATCH=0 で見張らない（前の形）。
"""
import os
import time

TICK_MS = 500
DRAG_STUCK_S = 1.5
STALL_LOG_S = 10.0


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_VIEW_PREP_WATCH') != '0'


def preparing(app):
    """前面のタブで表示の単位を組む仕事が残っているか（表示準備中）。"""
    try:
        return bool(getattr(app, '_analyze_units_only', False)
                    and app._analyze_pos < len(app._analyze_todo))
    except Exception:
        return False


def _alive(app, job):
    """after の予約がまだ Tk に残っているか。"""
    if job is None:
        return False
    try:
        return str(job) in [str(x) for x in app.root.tk.splitlist(app.root.tk.call('after', 'info'))]
    except Exception:
        return True       # 分からない時は生きているとみる（触らない）


def state(app):
    """記録に書く状態（本文は入れない）。"""
    try:
        tab = getattr(getattr(app, 'session', None), 'active', '?')
    except Exception:
        tab = '?'
    todo = getattr(app, '_analyze_todo', ()) or ()
    pos = getattr(app, '_analyze_pos', 0)
    return dict(tab=tab, left=max(0, len(todo) - pos), pos=pos,
                job=_alive(app, getattr(app, '_analyze_job', None)),
                after=_alive(app, getattr(app, '_after_id', None)),
                after_set=getattr(app, '_after_id', None) is not None,
                view_changing=bool(_safe(app._view_changing)),
                win_drag=bool(getattr(app, '_win_drag', None)),
                native_drag=bool(getattr(app, '_native_window_drag', False)),
                tab_warming=bool(getattr(app, '_tab_warming', False)),
                tab_job=_alive(app, getattr(app, '_tab_analysis_job', None)),
                warmup=getattr(app, '_warmup', None) is not None)


def detail(app):
    """小分けが回っているのに進まない時の、止まっている所（2026-11-17 2回目: 子は2つとも休み・小分けの予約は生きている
    のに、残り312のうち2で止まった）。本文は入れない。"""
    out = {}
    try:
        import analysis_async
        import analysis_work_app as input_work
        out['token_ok'] = input_work.token(app) == getattr(app, '_analyze_work', None)
        out['state_ok'] = analysis_async.state_key(app) == getattr(app, '_analyze_dependencies', None)
        pending = getattr(app, '_async_request', None)
        out['request'] = pending[0][0] if pending else None
        out['request_age'] = (round(time.monotonic() - getattr(app, '_async_request_at', time.monotonic()), 1)
                              if pending else None)
        flag = getattr(getattr(app, '_prefetch_worker', None), 'pause_flag', None)
        out['bg_paused'] = bool(flag.value) if flag is not None else None
        out['typed_pending'] = bool(_safe(app._typed_row_pending)) if hasattr(app, '_typed_row_pending') else None
        out['child_busy'] = child_busy(app)
    except Exception as error:
        out['detail_error'] = type(error).__name__
    try:
        import ime_speculation
        out['ime_waiting'] = bool(getattr(app, '_ime_speculation', None)) and bool(ime_speculation.pending(app)) \
            if hasattr(ime_speculation, 'pending') else None
    except Exception:
        out['ime_waiting'] = None
    inertia = getattr(app, '_scroll_inertia', None)
    out['held'] = bool(getattr(app, '_overview', None) is not None
                       or (getattr(app, '_drag', None) or {}).get('mode') == 'scroll'
                       or getattr(inertia, 'job', None) is not None)
    return out


HEAL_S = 5.0
BUSY_CPU_S = 0.5        # 見張りの間（5秒）に子がこれだけ CPU を使っていたら「計算している」


def _process_cpu(pid):
    """子のプロセスの CPU 時間（秒）。Windows だけ。分からなければ None。"""
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(ctypes.c_void_p(handle), *[ctypes.byref(t) for t in times]):
                return None
            return sum((t.dwHighDateTime << 32) + t.dwLowDateTime for t in times[2:]) / 1e7
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        return None


def child_cpu(app):
    """前面の子の CPU 時間（秒）・分からなければ None。"""
    worker = getattr(app, '_correction_worker', None)
    pid = getattr(getattr(worker, 'process', None), 'pid', None)
    return _process_cpu(pid) if pid else None


def child_busy(app):
    """止まってからの間に前面の子が計算していたか（True／False／分からない None）。"""
    w = getattr(app, '_view_prep_watch', None) or {}
    start, now = w.get('cpu_at_stall'), child_cpu(app)
    if start is None or now is None:
        return None
    return now - start >= BUSY_CPU_S


def heal(app, info):
    """小分けは回っているのに HEAL_S 秒進まない: 止まっている所を外す。戻り値は何をしたか（記録用）。
    ・本文か状態が答えを待っている時と変わった（line_step は黙って戻るだけ）→ 解析をやり直す
    ・前面の求め（行・段取り）の答えが来ないまま → その求めを取り消す（次の小分けが同じ行を求め直す）
    ・裏の子の一時停止の印が、打った行が無いのに立ったまま → 下ろす"""
    import analysis_async
    if info.get('token_ok') is False or info.get('state_ok') is False:
        app._analyze()
        return 'analyze'
    did = []
    if info.get('bg_paused') and not info.get('typed_pending'):
        try:
            analysis_async.pause_background(app, False)
            did.append('unpause')
        except Exception:
            pass
    # 子が計算している間は取り消さない（2026-11-17 18:26: 控えに済んでいない行が残ったタブは、表示準備中でも行を
    # 1行ずつ補正する。重い行は1行5秒を超え、取り消すと途中までの計算を捨てて、もう一度解き直していた）
    if (info.get('request') is not None and (info.get('request_age') or 0) >= HEAL_S
            and info.get('child_busy') is not True):
        try:
            analysis_async.cancel_foreground_request(app)
            did.append('cancel_request')
        except Exception:
            pass
    if info.get('held'):
        inertia = getattr(app, '_scroll_inertia', None)
        job = getattr(inertia, 'job', None)
        if job is not None and not _alive(app, job):
            inertia.job = None              # もう来ない慣性の予約（小分けは held の間は進まない）
            did.append('inertia')
    return '+'.join(did) or None


def _safe(fn):
    try:
        return fn()
    except Exception:
        return False


def log(app, what, info):
    try:
        import app as app_module
        if not app_module.redo_trace_on():
            return
        folder = getattr(app, '_scroll_trace_dir', None) or os.path.join(
            app_module.data_dir(), 'tools_local', 'scroll_trace')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, 'view_prep.log')
        try:
            if os.path.getsize(path) > 256 * 1024:
                with open(path, 'rb') as f:
                    f.seek(-128 * 1024, 2)
                    tail = f.read()
                with open(path, 'wb') as f:
                    f.write(tail[tail.find(b'\n') + 1:])
        except OSError:
            pass
        with open(path, 'a', encoding='utf-8') as f:
            f.write('%s  %s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), what,
                                      '  '.join('%s=%s' % kv for kv in info.items())))
    except Exception:
        pass


def arm(app):
    """表示準備中になった（小分けを予約した）: 見張りを1つだけ立てる。"""
    if not enabled() or getattr(app, '_view_prep_watch_job', None) is not None:
        return
    if not preparing(app):
        return
    w = app.__dict__.setdefault('_view_prep_watch', {})
    w.update(pos=getattr(app, '_analyze_pos', 0), since=time.monotonic(), drag_since=None, logged=False)
    try:
        app._view_prep_watch_job = app.root.after(TICK_MS, lambda: tick(app))
    except Exception:
        app._view_prep_watch_job = None


def tick(app, now=None):
    """500ms ごとの見張り。救ったら 'rescued'・印を下ろしたら 'drag_cleared'・何もしなければ None を返す。"""
    app._view_prep_watch_job = None
    if not enabled() or getattr(app, '_closing', False) or not preparing(app):
        return None
    now = time.monotonic() if now is None else now
    w = app.__dict__.setdefault('_view_prep_watch', dict(pos=None, since=now, drag_since=None, logged=False))
    pos = getattr(app, '_analyze_pos', 0)
    if pos != w.get('pos') or 'cpu_at_stall' not in w:
        w.update(pos=pos, since=now, logged=False, healed=False, cpu_at_stall=child_cpu(app))
    did = None
    # A: 窓のドラッグの印が立ったまま（ボタンは離れている）
    dragging = bool(getattr(app, '_win_drag', None) or getattr(app, '_native_window_drag', False))
    if dragging:
        if w.get('drag_since') is None:
            w['drag_since'] = now
        elif now - w['drag_since'] >= DRAG_STUCK_S and not _safe(app._window_drag_button_down):
            info = state(app)
            app._win_drag = None
            app._native_window_drag = False
            app._view_change_until = 0.0
            w['drag_since'] = None
            log(app, '窓のドラッグの印を下ろした', info)
            did = 'drag_cleared'
    else:
        w['drag_since'] = None
    # B: 小分けの続きも、入力の確かめの予約も、タブの切り替えの予約も生きていない
    if (not _alive(app, getattr(app, '_analyze_job', None))
            and not _alive(app, getattr(app, '_after_id', None))
            and not _alive(app, getattr(app, '_tab_analysis_job', None))):
        info = state(app)
        app._analyze_job = None
        if getattr(app, '_after_id', None) is not None:
            app._after_id = None              # もう来ない確かめの予約（小分けはこれが残ると続きを予約しない）
        try:
            app._schedule_analysis_chunk()
        except Exception:
            pass
        log(app, '小分けの続きを予約し直した', info)
        did = did or 'rescued'
    else:
        stalled = now - w.get('since', now)
        info = None
        busy = False
        if stalled >= HEAL_S and not w.get('healed') and os.environ.get('CN_VIEW_PREP_HEAL') != '0':
            info = dict(state(app), **detail(app))
            if info.get('child_busy') is True:
                # 子は計算している（重い行）: 止まりではない。次の5秒をまた見る
                w.update(since=now, cpu_at_stall=child_cpu(app))
                info = None
                busy = True
        if info is not None:
            w['healed'] = True
            what = None
            try:
                what = heal(app, info)
            except Exception as error:
                what = 'error:' + type(error).__name__
            log(app, '表示準備中が%d秒進まない→%s' % (int(HEAL_S), what or '外す所なし'), info)
            did = did or ('healed' if what else None)
        elif stalled >= STALL_LOG_S and not w.get('logged') and not busy:
            w['logged'] = True
            log(app, '表示準備中が10秒進まない', dict(state(app), **detail(app)))
    if getattr(app, '_view_prep_watch_job', None) is None:      # 予約し直した小分けが立てた見張りと二重にしない
        try:
            app._view_prep_watch_job = app.root.after(TICK_MS, lambda: tick(app))
        except Exception:
            app._view_prep_watch_job = None
    return did
