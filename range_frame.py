# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""A white frame around the copied range that shrinks into place (2026-10-23 うにさん).

「コピー範囲の白い枠: 1.4倍から0.3秒で本来の大きさへ縮む」. Text tags cannot draw it (a tag's
border is the size of the text, comes only with a background fill and is one box per line),
so thin lines are laid over the tk.Text as its own children (placed, not packed): the
inside stays open and no text is hidden. うにさん chose this (2026-10-23 「Aで進めて」) over a
transparent window. It goes away with the copy's other marks (a new copy, another tab, a scroll, Esc).

The frame follows the text (2026-10-23 うにさん): one rectangle per display line — the first from the
range's first letter, the last to its last letter, those between across the whole width, and a line
the range goes on past reaches the right edge of the text, where Tk paints the background of a wrapped
or ended line — and the outline of them all is drawn as one stepped shape, with no line inside it.
"""
import time
import tkinter as tk

STEP_MS = 15
FOLLOW_MS = 200        # measuring the range again while the frame is shown


def _text_right(widget):
    """x (widget coordinates) of the right edge of the text area."""
    inset = (widget.winfo_pixels(widget.cget('borderwidth')) + widget.winfo_pixels(widget.cget('highlightthickness'))
             + widget.winfo_pixels(widget.cget('padx')))
    return widget.winfo_width() - inset


def range_rows(widget, start, end):
    """[(x0, y0, x1, y1)] in widget coordinates, one per display line of [start, end) on screen.

    Measured per display line (2026-10-23 うにさん「コピー範囲の枠が、サイズがあっていない」): a long line
    wrapped into several display lines, and letters of different sizes (the part-of-speech fonts) give each
    display line its own height and width."""
    start, end = widget.index(start), widget.index(end)
    if widget.compare(end, '<=', start):
        return []
    try:
        height = widget.winfo_height()
        top = widget.index('@0,0 display linestart')
        bottom = widget.index('@0,%d display lineend' % max(0, height - 1))
        right_edge = _text_right(widget)
    except tk.TclError:
        return []
    here = widget.index(start + ' display linestart')
    if widget.compare(here, '<', top):
        here = top
    rows = []
    for _ in range(2000):                       # display lines on one screen; a guard, never reached
        if widget.compare(here, '>=', end) or widget.compare(here, '>', bottom):
            break
        following = widget.index(here + ' +1 display lines display linestart')
        last = not widget.compare(following, '>', here)
        # This display line's letters: up to the next display line, the end of its text line, the range's end
        tail = widget.index(here + ' lineend')
        if not last and widget.compare(following, '<', tail):
            tail = following
        goes_on = widget.compare(end, '>', tail)    # the range goes on past this display line
        if not goes_on:
            tail = end
        head = start if widget.compare(start, '>', here) else here
        info = widget.dlineinfo(head)
        a = widget.bbox(head)
        z = widget.bbox(widget.index(tail + ' -1c')) if widget.compare(tail, '>', head) else a
        if info is not None and a is not None and z is not None:
            x1 = max(z[0] + z[2], right_edge) if goes_on else z[0] + z[2]
            rows.append((a[0], info[1], x1, info[1] + info[3]))
        if last:
            break
        here = following
    return rows


def range_box(widget, start, end):
    """(x0, y0, x1, y1) inside the widget around the visible part of [start, end), or None."""
    rows = range_rows(widget, start, end)
    if not rows:
        return None
    return (min(r[0] for r in rows), min(r[1] for r in rows), max(r[2] for r in rows), max(r[3] for r in rows))


def outline(rows, pad=0):
    """The outline of the stacked rows as lines: [('h', x0, x1, y) or ('v', x, y0, y1)].

    Rows next to each other with the same width become one; where two rows meet, only the part of the
    boundary that is not shared by both is drawn (no line inside the shape)."""
    merged = []
    for x0, y0, x1, y1 in rows:
        if merged and (merged[-1][0], merged[-1][2]) == (x0, x1):
            merged[-1] = (x0, merged[-1][1], x1, y1)
        else:
            merged.append((x0, y0, x1, y1))
    if not merged:
        return []
    boxes = []
    for i, (x0, y0, x1, y1) in enumerate(merged):
        top = merged[i - 1][3] if i else y0 - pad          # rows touch: no gap between them
        bottom = y1 + pad if i == len(merged) - 1 else y1
        boxes.append((x0 - pad, top, x1 + pad, bottom))
    lines = [('h', boxes[0][0], boxes[0][2], boxes[0][1]), ('h', boxes[-1][0], boxes[-1][2], boxes[-1][3])]
    for x0, y0, x1, y1 in boxes:
        lines += [('v', x0, y0, y1), ('v', x1, y0, y1)]
    for upper, lower in zip(boxes, boxes[1:]):
        y = upper[3]
        a0, a1, b0, b1 = upper[0], upper[2], lower[0], lower[2]
        # the symmetric difference of [a0, a1] and [b0, b1]
        cuts = sorted({a0, a1, b0, b1})
        for left, right in zip(cuts, cuts[1:]):
            mid = (left + right) / 2.0
            if (a0 <= mid <= a1) != (b0 <= mid <= b1):
                lines.append(('h', left, right, y))
    return lines


class RangeFrame:
    def __init__(self):
        self.lines = []
        self.job = None
        self.widget = None
        self.color = '#ffffff'

    def show(self, widget, rows, color='#ffffff', width=2, start_scale=1.4, duration_ms=300, pad=2,
             measure=None, follow_ms=FOLLOW_MS):
        """Draw the frame around rows (widget coordinates; one (x0, y0, x1, y1) box is one row), from
        start_scale times its size down to it.

        measure() (when given) gives the rows again: while the frame is shown they are measured anew
        (2026-10-23 うにさん「コピー範囲の枠が、サイズがあっていない」 — the analysis gives the letters their
        part-of-speech sizes after the copy, and the lines move), at each step of the shrinking and then
        every follow_ms. Nothing from it (the range left the screen) hides the frame until it is back."""
        self.clear()
        rows = self._rows(rows)
        if not rows:
            return False
        self.widget, self.color = widget, color
        began = time.monotonic()
        current = [rows]

        def place(rows, scale):
            if not rows:
                self._lines(widget, 0)
                return
            x0 = min(r[0] for r in rows); y0 = min(r[1] for r in rows)
            x1 = max(r[2] for r in rows); y1 = max(r[3] for r in rows)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            scaled = [(cx + (a - cx) * scale, cy + (b - cy) * scale, cx + (c - cx) * scale, cy + (d - cy) * scale)
                      for a, b, c, d in rows]
            segments = outline(scaled, pad)
            frames = self._lines(widget, len(segments))
            # bbox/dlineinfo count from the Text's outer corner; place counts from inside its border, which for
            # a Text includes padx/pady (2026-10-23 うにさん「ずれています」: 14px right, 12px down in the memo)
            for frame, (kind, p, q, r) in zip(frames, segments):
                if kind == 'h':
                    left, right, y = int(round(p)), int(round(q)), int(round(r))
                    frame.place(x=left, y=y, width=right - left + width, height=width, bordermode='outside')
                else:
                    x, top, bottom = int(round(p)), int(round(q)), int(round(r))
                    frame.place(x=x, y=top, width=width, height=bottom - top + width, bordermode='outside')

        def measured():
            if measure is None:
                return current[0]
            try:
                return self._rows(measure())
            except tk.TclError:
                return []

        def step():
            self.job = None
            if self.widget is None:
                return
            done = 1.0 if duration_ms <= 0 else min(1.0, (time.monotonic() - began) * 1000.0 / duration_ms)
            eased = 1 - (1 - done) ** 2                  # quick at first, settling into place
            current[0] = measured() if done > 0 else current[0]
            try:
                place(current[0], start_scale + (1.0 - start_scale) * eased)
            except tk.TclError:
                self.clear()
                return
            if done < 1.0:
                self.job = widget.after(STEP_MS, step)
            elif measure is not None:
                self.job = widget.after(follow_ms, follow)

        def follow():
            self.job = None
            if self.widget is None:
                return
            rows = measured()
            if rows != current[0]:
                current[0] = rows
                try:
                    place(rows, 1.0)
                except tk.TclError:
                    self.clear()
                    return
            self.job = widget.after(follow_ms, follow)
        step()
        return True

    @staticmethod
    def _rows(rows):
        if not rows:
            return []
        if len(rows) == 4 and all(isinstance(v, (int, float)) for v in rows):
            return [tuple(rows)]                     # one box
        return [tuple(r) for r in rows]

    def _lines(self, widget, count):
        while len(self.lines) > count:
            try:
                self.lines.pop().destroy()
            except tk.TclError:
                pass
        while len(self.lines) < count:
            self.lines.append(tk.Frame(widget, bg=self.color, bd=0, highlightthickness=0, cursor='xterm'))
        return self.lines

    def clear(self):
        if self.job is not None and self.widget is not None:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
        self.job = None
        for line in self.lines:
            try:
                line.destroy()
            except tk.TclError:
                pass
        self.lines = []
        self.widget = None

    def place_of(self):
        """(x, y, width, height) of each line, for tests."""
        out = []
        for line in self.lines:
            info = line.place_info()
            out.append(tuple(int(info.get(k, 0) or 0) for k in ('x', 'y', 'width', 'height')))
        return out
