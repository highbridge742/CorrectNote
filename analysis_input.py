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

# The row is computed from the keystroke itself (2026-10-17, うにさん「打った分を
# 可能な限り早く補正する」): a newer key supersedes the computation in the child,
# and the display still waits for the quiet period. It was 80ms.
COMPUTE_DELAY_MS = 1
DISPLAY_QUIET_MS = 300
# After an IME commit the phrase is done, so its correction need not wait as
# long as after a single key (2026-10-17, provisional until うにさん decides:
# 案C, the commit only; single keys keep DISPLAY_QUIET_MS).
DISPLAY_QUIET_IME_MS = 100


def quiet_ms(app):
    """The display pause for the edit being scheduled: an edit while an IME
    composition is live (app._ime_comp, kept by the IME watcher until it sees
    the composition end) is the commit itself. Right after it, the watcher
    binds the committed reading and ends the composition without changing the
    text; that follow-up keeps the commit's pause (it reset it to 300ms)."""
    try:text=app.editor_source_text()
    except Exception:text=None
    if getattr(app,'_ime_comp',''):
        app._input_ime_text=text
        return DISPLAY_QUIET_IME_MS
    if text is not None and text==getattr(app,'_input_ime_text',None):
        return DISPLAY_QUIET_IME_MS
    app._input_ime_text=None
    return DISPLAY_QUIET_MS


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
        app._input_display_after=time.monotonic()+quiet_ms(app)/1000
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
