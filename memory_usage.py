# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Memory usage tiers: how many correction engines exist and how long they stay.

2026-10-14 うにさん: three tiers with upper limits on the total of every
CorrectNote process in Task Manager, analysis included — low 700MB, mid
1400MB, high 2100MB; the default is high. Low may analyse very slowly.
2026-10-20 うにさん: the default is now mid (a safety step while PCs were crashing).
2026-10-15 うにさん: 「中と高は、もう一段階負荷をかけてよいです。中は高に
寄せた処理で1500前後に。高も何かひとつ追加してよいです。低は900を目指す
というよりかは、限界まで抑えるという方針です。そのうえで900ならよい。」

    high  Correction runs in worker processes, kept ready: the open tab's
          worker (with idle warm-up), a background worker for the other
          tabs, the quick-input worker. The main process preloads tables.
          Completed values (results, display units, prepared contexts) are
          kept for every open tab, so returning to any tab costs nothing.
    mid   Like high with one child: the open tab's worker is kept ready
          (warm-up, preloaded main tables), and the other tabs are analysed
          in the background by that same worker whenever the open tab has
          nothing in flight (no second child). The quick-input worker still
          closes 5 seconds after its last result.
    low   One worker at a time, closed 5 seconds after its last result; no
          background tabs, no warm-up, no preloading. The worker and the main
          process keep their largest public tables in compact form
          (compact_tables: same answers, slower lookups; the main process
          starts workers with CN_COMPACT_TABLES=1). Only the open tab keeps
          its analysis results and display units.

Measured 2026-10-14 (tools_local/v114_memory/WORK.md): a worker process
needs about 450-550MB by itself even with compact tables. Running the engine
inside the main process was tried twice and dropped: on the Tk thread it
froze the window (36 seconds); on a second thread it crashed the process
(access violation) in 2 of 3 runs.
"""
import os
import traceback

from settings import MEMORY_LOW, MEMORY_MID, MEMORY_HIGH


IDLE_RELEASE_MS = 5000
_FIELDS = {
    'foreground': ('_correction_worker', '_worker_state', '_memory_foreground_job'),
    'quick': ('_quick_worker', '_quick_worker_state', '_memory_quick_job'),
}
_TIERS = (MEMORY_LOW, MEMORY_MID, MEMORY_HIGH)


def mode(app):
    """The saved tier; anything unknown is treated as the default (mid)."""
    settings = getattr(app, 'settings', None)
    value = settings.get('memory_usage') if settings is not None else None
    return value if value in _TIERS else MEMORY_MID


def low(app):
    """The saving tier itself (compact tables, nothing kept ready)."""
    return mode(app) == MEMORY_LOW


def compact(app):
    """Low only: the workers (and the main process) keep their largest
    public tables in compact form."""
    return mode(app) == MEMORY_LOW


def retains(app, channel):
    """Whether an idle child of `channel` ('foreground' or 'quick') stays
    open. High keeps both; mid keeps the open tab's child and closes the
    quick-input child; low closes both after their quiet period."""
    tier = mode(app)
    if tier == MEMORY_HIGH:
        return True
    if tier == MEMORY_MID:
        return channel == 'foreground'
    return False


def shares_worker(app):
    """Mid: the other tabs are analysed by the open tab's child while it is
    idle, instead of by a second child."""
    return mode(app) == MEMORY_MID


def prefetch_worker(app):
    """High only: a separate child for the other tabs."""
    return mode(app) == MEMORY_HIGH


def background_tabs(app):
    """Whether the other tabs are analysed before they are visited."""
    return mode(app) in (MEMORY_HIGH, MEMORY_MID)


def prewarm(app):
    """Whether the open tab's child loads its public tables ahead of use."""
    return mode(app) in (MEMORY_HIGH, MEMORY_MID)


def preloads(app):
    """Whether the main process reads its optional public tables at start."""
    return mode(app) in (MEMORY_HIGH, MEMORY_MID)


def quick_prepare(app):
    """High only: the quick-input child is prepared when the window opens."""
    return mode(app) == MEMORY_HIGH


def open_tabs(app):
    try:
        return len(app.session.tabs)
    except Exception:
        return 0


def cache_tabs(app, default):
    """Tabs whose completed analysis results the main process keeps.
    Low: the open tab only. Mid: `default` (the former limit). High: every
    open tab (2026-10-15 うにさん「高も何かひとつ追加してよい」)."""
    tier = mode(app)
    if tier == MEMORY_LOW:
        return 1
    if tier == MEMORY_HIGH:
        return max(default, open_tabs(app))
    return default


def units_cache_tabs(app):
    """Other tabs whose display units are kept: low none, mid 3, high all.

    Measured 2026-10-15 (6 public tabs, low): the parked units of one other
    tab cost the main process about 28MB; the open tab's own units stay."""
    tier = mode(app)
    if tier == MEMORY_LOW:
        return 0
    if tier == MEMORY_HIGH:
        return max(3, open_tabs(app))
    return 3


def completed_tabs(app):
    """Open tabs whose completed values (results, context, units) the main
    process keeps for an instant return: low only the open tab (about 40MB
    for five other long tabs, measured 2026-10-15); otherwise every tab."""
    return 1 if mode(app) == MEMORY_LOW else None


def context_cache_size(app):
    """Prepared document contexts kept by the main process: 4, or one per
    open tab in high."""
    if mode(app) == MEMORY_HIGH:
        return max(4, open_tabs(app))
    return 4


def export_env(app):
    """Tell workers started from now on which table form to use.

    A spawned worker inherits the main process's environment when it starts,
    so this is set before any worker of the current tier is created."""
    import compact_tables
    if compact(app):
        os.environ[compact_tables.ENV] = '1'
    else:
        os.environ.pop(compact_tables.ENV, None)


# Public tables the correction workers use. The main process only needs them
# for right-click candidates and explanations, and each module loads itself on
# first use. High and mid preload them for speed; low leaves them unloaded
# (about 120MB less in the main process, measured 2026-10-14; first use waits
# ~0.6s).
OPTIONAL_PRELOAD = ('seed_japanese', 'oddness')


def preload_tables(app):
    """Warm up the optional public tables in the main process (not in low).

    Returns the names that were loaded. Called from the warmup thread."""
    if not preloads(app):
        return ()
    import importlib
    loaded = []
    for name in OPTIONAL_PRELOAD:
        try:
            importlib.import_module(name).available()
            loaded.append(name)
        except Exception:
            pass
    return tuple(loaded)


def cancel_job(app, name):
    identifier = getattr(app, name, None)
    if identifier is not None:
        try:
            app.root.after_cancel(identifier)
        except Exception:
            pass
    setattr(app, name, None)


def cancel_release(app, channel):
    cancel_job(app, _FIELDS[channel][2])


def cancel_releases(app):
    for channel in _FIELDS:
        cancel_release(app, channel)


def _busy(app, channel):
    if channel == 'foreground':
        pending = getattr(app, '_foreground_analysis_pending', None)
        return (getattr(app, '_async_request', None) is not None
                or getattr(app, '_async_context_scope', None) is not None
                or (callable(pending) and pending()))
    return any(getattr(app, name, None) is not None for name in (
        '_quick_job', '_quick_after_id', '_quick_prepare_after_id',
        '_quick_f2_pending'))


def foreground_busy(app):
    """The open tab has correction work in flight or about to start."""
    return _busy(app, 'foreground')


def queue_release(app, channel, delay=IDLE_RELEASE_MS):
    """Close only the same idle child, after its result has reached the UI."""
    if retains(app, channel) or getattr(app, '_closing', False):
        return
    worker_name, state_name, job_name = _FIELDS[channel]
    worker = getattr(app, worker_name, None)
    if worker is None:
        return
    cancel_release(app, channel)

    def release():
        if getattr(app, job_name, None) != identifier:
            return
        setattr(app, job_name, None)
        if (retains(app, channel) or getattr(app, '_closing', False)
                or getattr(app, worker_name, None) is not worker):
            return
        if _busy(app, channel):
            queue_release(app, channel, delay)
            return
        try:
            worker.close()
        except Exception:
            traceback.print_exc()
            return
        setattr(app, worker_name, None)
        # The next request must supply the complete latest model snapshot.
        setattr(app, state_name, None)
        if channel == 'quick':
            app._quick_composition_prepared = False

    identifier = app.root.after(delay, release)
    setattr(app, job_name, identifier)


def switch_tables(app, previous):
    """After a tier change into or out of low, drop idle workers so the next
    one starts with the table form of the new tier. A busy one finishes
    first; low then closes it after its quiet period, as usual."""
    export_env(app)
    if (previous == MEMORY_LOW) == compact(app):
        return
    for channel, (worker_name, state_name, _) in _FIELDS.items():
        worker = getattr(app, worker_name, None)
        if worker is None or _busy(app, channel):
            continue
        cancel_release(app, channel)
        try:
            worker.close()
        except Exception:
            traceback.print_exc()
            continue
        setattr(app, worker_name, None)
        setattr(app, state_name, None)
        if channel == 'quick':
            app._quick_composition_prepared = False


def apply_tier(app):
    """After a tier change, once the UI has parked its background rows:
    keep or release the children as the new tier says and start its
    preparation. The UI then queues the background tabs itself where the
    tier has them."""
    cancel_releases(app)
    for name in ('_idle_prewarm_job', '_quick_prepare_after_id',
                 '_quick_prewarm_after_id', '_quick_idle_after_id'):
        cancel_job(app, name)
    if not prefetch_worker(app):
        worker = getattr(app, '_prefetch_worker', None)
        if worker is not None:
            try:
                worker.close()
            except Exception:
                traceback.print_exc()
        app._prefetch_worker = None
        app._prefetch_worker_state = None
        app._async_background_request = None
    queue_release(app, 'foreground')
    queue_release(app, 'quick')
    if prewarm(app):
        import analysis_async
        analysis_async.prewarm(app)
        analysis_async.queue_idle_prewarm(app)
    if quick_prepare(app):
        import quick_analysis
        quick_analysis.schedule_prepare(app)


# The former name (entering mid or low from high); kept for tools.
apply_low = apply_tier
