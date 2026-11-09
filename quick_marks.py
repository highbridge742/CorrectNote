# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""簡易入力の未解析の印（2026-11-05 うにさん「変えた行だけ」）。

打った行・変えた行だけ、答えが出るまで左端に細い縦線を出す。行番号は無い。本体の未解析の印と同じ色。
簡易入力は全部の行をまとめて解析するので、行ごとの進み具合は無い。前に答えが出た時の本文と比べて、違う行に出す。
本文には何も足さない（欄の左の余白に置いた細い Canvas に描く）。"""
import tkinter as tk

WIDTH = 3
LEFT = 2
GAP = 2         # 縦線と本文の字のあいだ（2026-11-07 うにさん「未解析の縦線が、文字に被っている」）


def changed_rows(answered, lines):
    """前に答えが出た本文と比べて、変わった行（1から）。空の行には出さない。"""
    if answered is None:
        return {row for row, line in enumerate(lines, 1) if line.strip()}
    head = 0
    limit = min(len(answered), len(lines))
    while head < limit and answered[head] == lines[head]:
        head += 1
    tail = 0
    while tail < limit - head and answered[-1 - tail] == lines[-1 - tail]:
        tail += 1
    return {row + 1 for row in range(head, len(lines) - tail) if lines[row].strip()}


class QuickMarks:
    def __init__(self, text, color):
        self.text = text
        self.color = color          # 色は描く時に尋ねる（配色の切り替えに付いていく）
        self.answered = None
        self.pending = set()
        self.canvas = None
        self.job = None
        self.shown = False
        observers = getattr(text, '_correctnote_observers', None)
        if observers is not None:
            observers.setdefault('scrolled', []).append(self.queue)
        text.bind('<Configure>', self.queue, add=True)

    def note_change(self, event=None):
        """本文が変わった（打鍵の時に呼ぶ）。"""
        try:
            self.pending = changed_rows(self.answered, self.text.get('1.0', 'end-1c').split('\n'))
        except tk.TclError:
            return
        self.queue()

    def answered_for(self, source):
        """この本文の答えが出た。"""
        self.answered = source.split('\n')
        self.note_change()

    def queue(self, event=None):
        if self.job is None and (self.pending or self.shown):
            try:
                self.job = self.text.after_idle(self.draw)
            except tk.TclError:
                self.job = None

    def _canvas(self):
        if self.canvas is None:
            cv = tk.Canvas(self.text, highlightthickness=0, bd=0, cursor='', takefocus=0)
            cv._correctnote_paper_below = True      # typing_pointer: 欄の一部として扱う
            cv.bind('<ButtonPress-1>', self._press)
            # ホイールも欄へ（細い線の上で回しても、欄の上で回したのと同じ）
            cv.bind('<MouseWheel>', lambda e: __import__('appearance').forward_wheel(e, self.text))
            self.canvas = cv
        return self.canvas

    def _spot(self):
        """(place の x, 描く時の縦のずらし)。place は本文の内側の左上が 0。

        縦は本文の内側に収める（y=0・欄の高さ）: 内側の外まで伸ばした置き方（2026-11-07 朝）のあと、簡易入力の窓を
        閉じる時に Tk の destroy の中で落ちることが増えた（試験 34回で5回、前の置き方は20回で0回）。dlineinfo の y は
        欄の外枠から数えるので、描く時に (枠＋pady) を引く。横は字の手前 GAP の余白の中。"""
        text = self.text
        edge = int(text.winfo_pixels(text.cget('borderwidth'))) + int(text.winfo_pixels(text.cget('highlightthickness')))
        padx = int(text.winfo_pixels(text.cget('padx')))
        pady = int(text.winfo_pixels(text.cget('pady')))
        # 欄の外枠から数えた左端: 字の手前 GAP、ただし枠の内側 LEFT より左へは出さない
        left = max(edge + LEFT, edge + padx - GAP - WIDTH)
        return left - (edge + padx), -(edge + pady)

    def _press(self, event):
        # 細い線の上を押しても、左の余白を押したのと同じ
        try:
            x, y = event.x + event.widget.winfo_x(), event.y + event.widget.winfo_y()
            self.text.event_generate('<ButtonPress-1>', x=x, y=y)
            self.text.event_generate('<ButtonRelease-1>', x=x, y=y)
        except tk.TclError:
            pass
        return 'break'

    def draw(self):
        self.job = None
        text = self.text
        try:
            if not text.winfo_exists():
                return
            bars = []
            for row in sorted(self.pending):
                info = text.dlineinfo(f'{row}.0')
                if info is None:
                    continue
                last = text.dlineinfo(f'{row}.end') or info     # 折り返した行の下の端まで
                bars.append((info[1] + 1, last[1] + last[3] - 1))
            if not bars:
                if self.shown and self.canvas is not None:
                    self.canvas.place_forget()
                    self.shown = False
                return
            cv = self._canvas()
            cv.delete('all')
            cv.configure(bg=text.cget('background'))
            color = self.color()
            x, dy = self._spot()
            for top, bottom in bars:
                cv.create_rectangle(0, top + dy, WIDTH, bottom + dy, outline='', fill=color)
            if not self.shown or getattr(self, '_placed', None) != x:
                # Text の place は本文の内側（枠＋余白 padx・pady の内側）が 0。本文の左の余白の中、字から GAP あけた所
                cv.place(x=x, y=0, width=WIDTH, relheight=1)
                self._placed = x
                self.shown = True
        except tk.TclError:
            pass
