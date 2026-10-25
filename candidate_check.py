# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Check the reconversion list's typo candidates in the background (2026-10-23 うにさん).

「再変換候補の一覧の『打ち間違いの可能性』の候補: その単語に置き換えた文を解析して紫の判定に
なるなら表示しない」. The list opens without them; each candidate's line (the word replaced by
it) is then analysed one at a time, and only those whose replaced word is not marked purple are
added. The judgement is the engine's own: the same line task as the document (correct_line in
analysis_worker) and the same purple shown on the memo (corrector.visible_odd_spans, minus what
a correction already covers). Nothing in the correction itself changes here.

It runs in a child process of its own (analysis_worker.Worker), so the document's analysis is
neither waited for nor superseded, and Tk is never held up. The child is started on the first
check and closed when the app closes or after IDLE_CLOSE_MS without checks.
"""
import keyboard_layout

POLL_MS = 20
IDLE_CLOSE_MS = 60000


class CandidateCheck:
    def __init__(self, app):
        self.app = app
        self.worker = None
        self.state = None
        self.jobs = []          # (line, start, surface, on_pass)
        self.current = None     # (request id, job)
        self.after_id = None
        self.idle_id = None
        self.generation = 0
        self.on_done = None

    # --- public --------------------------------------------------------
    def start(self, line, items, on_pass, on_done=None):
        """items: [(start, end, candidate)] for one row's text `line`. on_pass(candidate) runs in Tk
        for each candidate whose replaced word is not purple, in the given order; on_done() once
        all are checked (not when cancelled)."""
        self.cancel()
        self.generation += 1
        generation = self.generation
        self.on_done = (lambda: generation == self.generation and on_done()) if on_done else None
        for start, end, candidate in items:
            surface = candidate.get('surface') or ''
            if not surface:
                continue
            new_line = line[:start] + surface + line[end:]
            self.jobs.append((new_line, start, surface,
                              lambda c=candidate: generation == self.generation and on_pass(c)))
        self._schedule(0)

    def cancel(self):
        """The list closed: stop checking (the child keeps running for the next list)."""
        self.generation += 1
        self.jobs = []
        self.on_done = None
        if self.current is not None and self.worker is not None:
            try:
                if self.worker.process.is_alive():
                    self.worker.submit(dict(kind='cancel'))
            except Exception:
                pass
        self.current = None
        if self.after_id is not None:
            try:
                self.app.root.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        self._schedule_idle_close()

    def close(self):
        self.cancel()
        if self.idle_id is not None:
            try:
                self.app.root.after_cancel(self.idle_id)
            except Exception:
                pass
            self.idle_id = None
        if self.worker is not None:
            try:
                self.worker.close()
            except Exception:
                pass
        self.worker = None
        self.state = None

    # --- the judgement ------------------------------------------------
    @staticmethod
    def purple_at(result, line, start, end, decisions):
        """Is [start, end) of `line` shown purple for this engine result (as the memo shows it)?"""
        import corrector, ui_projection
        fixed = list(ui_projection.corrections(result)) if result.get('changed') else []
        for a, z in corrector.visible_odd_spans(line, result.get('odd_spans', ()), decisions):
            if any(a < right and left < z for left, right, _detail in fixed):
                continue
            if a < end and start < z:
                return True
        return False

    # --- running -----------------------------------------------------
    def _schedule(self, delay):
        if self.after_id is None and not getattr(self.app, '_closing', False):
            try:
                self.after_id = self.app.root.after(delay, self._step)
            except Exception:
                self.after_id = None

    def _schedule_idle_close(self):
        if self.idle_id is not None:
            try:
                self.app.root.after_cancel(self.idle_id)
            except Exception:
                pass
            self.idle_id = None
        if self.worker is not None and not getattr(self.app, '_closing', False):
            try:
                self.idle_id = self.app.root.after(IDLE_CLOSE_MS, self.close)
            except Exception:
                self.idle_id = None

    def _task(self, line):
        app = self.app
        return dict(kind='line', line=line, result=app._blank_result(line),
                    context=getattr(app, '_analyze_ctx', None),
                    input_method=(app.settings.get('input_method') or 'kana'),
                    keyboard=keyboard_layout.spec(app.settings), nearby=(),
                    recent=app.recent_words.words() if getattr(app, 'recent_words', None) is not None else (),
                    readings=(), calculations=(), attested=getattr(app, '_attested_surfaces', {}))

    def _submit(self, job):
        from analysis_worker import Worker, snapshot, state_key
        app = self.app
        if self.worker is not None and not self.worker.process.is_alive():
            self.worker.close()
            self.worker = None
        if self.worker is None:
            self.worker = Worker()
            self.state = None
        state = state_key(app)
        data = snapshot(app) if self.state != state else None
        if data is not None:
            data['_state_identity'] = state
        identifier = self.worker.submit(self._task(job[0]), data)
        self.state = state
        self.current = (identifier, job)

    def _step(self):
        self.after_id = None
        if getattr(self.app, '_closing', False):
            return
        if self.idle_id is not None:
            try:
                self.app.root.after_cancel(self.idle_id)
            except Exception:
                pass
            self.idle_id = None
        try:
            if self.current is None:
                if not self.jobs:
                    done, self.on_done = self.on_done, None
                    if done is not None:
                        done()
                    self._schedule_idle_close()
                    return
                self._submit(self.jobs.pop(0))
            identifier, job = self.current
            value = self.worker.poll(identifier)
            if value is None:
                self._schedule(POLL_MS)
                return
            self.current = None
            line, start, surface, on_pass = job
            result = value.get('result') or {}
            if not self.purple_at(result, line, start, start + len(surface),
                                  getattr(self.app, 'decisions', None)):
                on_pass()
        except Exception:
            # A failed check shows nothing more; the list stays as it is.
            import traceback
            traceback.print_exc()
            self.current = None
            self.jobs = []
            if self.worker is not None:
                try:
                    self.worker.close()
                except Exception:
                    pass
                self.worker = None
                self.state = None
            return
        self._schedule(0)
