# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retain correction workers for speed, or release them after quiet completion."""
import traceback

from settings import MEMORY_LOW


IDLE_RELEASE_MS = 5000
_FIELDS = {
    'foreground': ('_correction_worker', '_worker_state', '_memory_foreground_job'),
    'quick': ('_quick_worker', '_quick_worker_state', '_memory_quick_job'),
}


def low(app):
    settings = getattr(app, 'settings', None)
    return settings is not None and settings.get('memory_usage') == MEMORY_LOW


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


def queue_release(app, channel, delay=IDLE_RELEASE_MS):
    """Close only the same idle child, after its result has reached the UI."""
    if not low(app) or getattr(app, '_closing', False):
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
        if (not low(app) or getattr(app, '_closing', False)
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


def apply_low(app):
    """Discard optional preparation after the UI has parked background rows."""
    cancel_releases(app)
    for name in ('_idle_prewarm_job', '_quick_prepare_after_id',
                 '_quick_prewarm_after_id', '_quick_idle_after_id'):
        cancel_job(app, name)
    worker = getattr(app, '_prefetch_worker', None)
    if worker is not None:
        worker.close()
    app._prefetch_worker = None
    app._prefetch_worker_state = None
    app._async_background_request = None
    queue_release(app, 'foreground')
    queue_release(app, 'quick')
