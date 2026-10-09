# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Compute during the input pause; keep the existing quiet period for display.

Only the current generation/deadline is retained in memory, never input history.
"""
import math
import time
import tkinter as tk
import analysis_work_app as input_work
from analysis_worker import state_key

COMPUTE_DELAY_MS = 80
DISPLAY_QUIET_MS = 300


def identity(app):
    return input_work.token(app), state_key(app)


def cancel_display(app):
    job=getattr(app,'_input_display_job',None)
    if job is not None:
        try:app.root.after_cancel(job)
        except tk.TclError:pass
    app._input_display_job=None
    app._input_display_learn=False


def schedule(app):
    current=identity(app)
    changed=current!=getattr(app,'_input_pause_identity',None)
    ime_pending=getattr(app,'_unified_autofix_waiting_ime',False)
    if not changed and not ime_pending:
        return  # Arrow/selection key releases must not postpone ongoing work.
    if changed or ime_pending:
        cancel_display(app)
        app._input_pause_identity=current
        app._input_display_after=time.monotonic()+DISPLAY_QUIET_MS/1000
    job=getattr(app,'_after_id',None)
    if job is not None:app.root.after_cancel(job)
    app._after_id=app.root.after(COMPUTE_DELAY_MS,app._analyze_if_changed)


def defer_display(app,learn):
    expected=getattr(app,'_input_pause_identity',None)
    if expected is None:return False
    current=identity(app)
    if current!=expected:return False
    remaining=getattr(app,'_input_display_after',0)-time.monotonic()
    job=getattr(app,'_input_display_job',None)
    if remaining<=0 and job is None:return False
    app._input_display_learn=bool(learn or getattr(app,'_input_display_learn',False))
    if job is not None:return True
    def ready():
        app._input_display_job=None
        wanted_learning=getattr(app,'_input_display_learn',False)
        app._input_display_learn=False
        if (getattr(app,'_closing',False) or identity(app)!=current
                or getattr(app,'_analyze_work',None)!=current[0]
                or getattr(app,'_analyze_dependencies',None)!=current[1]
                or getattr(app,'_analyze_text',None)!=app.editor_source_text()):
            return
        # A deadline is not permission to redraw during a held/dragged view.
        drag=getattr(app,'_drag',None)
        if (app._view_changing() or getattr(app,'_overview',None) is not None
                or (drag and drag.get('mode')=='scroll')):
            app._input_display_learn=wanted_learning
            app._input_display_job=app.root.after(50,ready)
            return
        app._refresh_after_analysis(learn=wanted_learning)
        app._queue_status_visibility()
    app._input_display_job=app.root.after(max(1,math.ceil(remaining*1000)),ready)
    return True
