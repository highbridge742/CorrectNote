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
import os
import time
from collections import OrderedDict

import keyboard_layout

POLL_MS = 20
IDLE_CLOSE_MS = 60000
# 確かめた答えの控え（2026-11-14 うにさん「再変換の、候補が順に出た後、一度閉じて再度選択すると候補を作り直している。
# 少し前のは覚えておくはず」）。同じ行の文・同じ所・同じ候補・同じ入力方式なら、少し前の答え（通った／紫になった）を
# すぐ使い、まだ確かめていない物だけ確かめる。途中で閉じても、確かめ終えた分は残る。行の文が変われば鍵が変わる。
# メモリだけ（ファイルには書かない）。CN_TYPO_CHECK_MEMO=0 で前の形（開くたびに全部確かめる）
MEMO_LIMIT = 512
MEMO_SEC = 600


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
        self.memo = OrderedDict()   # (行, 始め, 語, 入力方式, 配列) → (通ったか, 時刻)

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
            known = self._remembered(new_line, start, surface)
            if known is True:
                on_pass(candidate)      # 少し前に通った: すぐ出す
                continue
            if known is False:
                continue                # 少し前に紫になった: 出さない
            self.jobs.append((new_line, start, surface,
                              lambda c=candidate: generation == self.generation and on_pass(c)))
        self._schedule(0)

    # --- the memo of answers -----------------------------------------
    def _memo_key(self, line, start, surface):
        settings = getattr(self.app, 'settings', None)
        try:
            method = settings.get('input_method') or 'kana'
            layout = repr(keyboard_layout.spec(settings))
        except Exception:
            method, layout = None, None
        return (line, start, surface, method, layout)

    def _remembered(self, line, start, surface):
        """少し前に確かめた答え（True 通った・False 紫）。無い・古い・切ってあるなら None。"""
        if os.environ.get('CN_TYPO_CHECK_MEMO') == '0':
            return None
        key = self._memo_key(line, start, surface)
        got = self.memo.get(key)
        if got is None:
            return None
        if time.monotonic() - got[1] > MEMO_SEC:
            del self.memo[key]
            return None
        self.memo.move_to_end(key)
        return got[0]

    def _remember(self, line, start, surface, passed):
        if os.environ.get('CN_TYPO_CHECK_MEMO') == '0':
            return
        self.memo[self._memo_key(line, start, surface)] = (bool(passed), time.monotonic())
        while len(self.memo) > MEMO_LIMIT:
            self.memo.popitem(last=False)

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
            passed = not self.purple_at(result, line, start, start + len(surface),
                                        getattr(self.app, 'decisions', None))
            self._remember(line, start, surface, passed)
            if passed:
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
