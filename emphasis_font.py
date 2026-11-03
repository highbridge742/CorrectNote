# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Show a range of a tk.Text in a larger font for a while (2026-10-23 うにさん).

Used for the copied range (コピーした範囲を1.2倍) and the search hits while the
search window is open (検索の候補文字を1.3倍). Only Text tags with a font: no
drawing over the text (うにさん 2026-10-19: no Canvas/Label laid over it).

The range keeps what each character already shows — the size per part of speech
(pos_font), bold/italic (text_format), the pane font — and is that times the
factor: it is cut where the font-bearing tags change, and each piece gets a tag
with its own font scaled. The tags are raised above all others while shown.
"""
import tkinter as tk
from tkinter import font as tkfont

PREFIX = 'emph_'          # every tag of this module; callers add their own word (emph_copy, emph_find)


def _font_tags(widget):
    """The tags that set a font, with their fonts ({tag: spec})."""
    fonts = {}
    for tag in widget.tag_names():
        if tag.startswith(PREFIX) or tag == 'sel':
            continue
        spec = widget.tag_cget(tag, 'font')
        if spec:
            fonts[tag] = spec
    return fonts


def _font_of(widget, index, fonts):
    """The font the character at index is drawn with (highest tag with a font, else the pane's)."""
    for tag in reversed(widget.tag_names(index)):
        spec = fonts.get(str(tag))
        if spec:
            return spec
    return widget.cget('font')


def _position(index):
    return tuple(int(p) for p in str(index).split('.'))


def _cuts(widget, start, end, fonts):
    """Indexes where the font-bearing tags begin or end inside [start, end]."""
    start, end = str(widget.index(start)), str(widget.index(end))
    points = {start, end}
    low, high = _position(start), _position(end)
    # One question for the range: its tag changes. Asking each tag cost about 340 Tk calls a hit
    # (2026-11-02: Find Next on a frequent character held the window 2.4 s for its 500 marks).
    for kind, tag, index in widget.dump(start, end, tag=True):
        if kind in ('tagon', 'tagoff') and tag in fonts and low < _position(index) < high:
            points.add(str(index))
    return sorted(points, key=_position)


def apply_many(widget, ranges, factor, prefix):
    """Show each [start, end) at `factor` times its own font, in one batch. Returns the number of pieces."""
    if factor == 1:
        return 0
    cache = widget.__dict__.setdefault('_correctnote_emphasis_fonts', {})
    fonts = _font_tags(widget)
    actuals = {}
    spans = {}
    pieces = 0
    for start, end in ranges:
        if widget.compare(start, '>=', end):
            continue
        points = _cuts(widget, start, end, fonts)
        for a, z in zip(points, points[1:]):
            if not widget.compare(a, '<', z):
                continue
            spec = str(_font_of(widget, a, fonts))
            actual = actuals.get(spec)
            if actual is None:
                actual = actuals[spec] = tkfont.Font(root=widget, font=spec).actual()
            size = int(actual.get('size') or 10)
            scaled = int(round(size * factor)) or (1 if size > 0 else -1)
            style = tuple(s for s in (actual.get('weight'), actual.get('slant'))
                          if s in ('bold', 'italic'))
            key = (prefix, actual.get('family'), scaled) + style
            tag = cache.get(key)
            if tag is None:
                tag = cache[key] = '%s%d' % (prefix, len([k for k in cache if k[0] == prefix]))
            if tag not in spans:
                widget.tag_configure(tag, font=(actual.get('family'), scaled) + style)
                spans[tag] = []
            spans[tag].extend((a, z))
            pieces += 1
    for tag, indexes in spans.items():
        widget.tag_add(tag, *indexes)
        widget.tag_raise(tag)
    return pieces


def apply(widget, start, end, factor, prefix):
    """Show [start, end) at `factor` times its own font. Returns the number of pieces."""
    return apply_many(widget, ((start, end),), factor, prefix)


def clear(widget, prefix):
    """Back to the usual fonts."""
    try:
        for tag in widget.tag_names():
            if tag.startswith(prefix):
                widget.tag_remove(tag, '1.0', 'end')
    except tk.TclError:
        pass


def shown(widget, prefix):
    try:
        return any(tag.startswith(prefix) and widget.tag_ranges(tag) for tag in widget.tag_names())
    except tk.TclError:
        return False


def partial_lines_only(widget, start, end):
    """True when no line of [start, end) is taken whole (2026-10-23 うにさん「コピー範囲が行の
    一部だけなら…行全体を含む行があるコピーでは掛けない」). An empty line counts as whole."""
    first = int(widget.index(start).split('.')[0])
    last_index = widget.index(end)
    last = int(last_index.split('.')[0])
    if widget.compare(last_index, '==', last_index + ' linestart') and last > first:
        last -= 1                      # ends at the head of the next line: up to the line before
    for row in range(first, last + 1):
        head, tail = '%d.0' % row, '%d.end' % row
        a = head if widget.compare(start, '<=', head) else start
        z = tail if widget.compare(end, '>=', tail) else end
        if widget.compare(a, '==', head) and widget.compare(z, '==', tail):
            return False
    return True
