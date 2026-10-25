# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Where to put Quick Input or the word book next to the mouse pointer without covering the other
one (2026-10-23 うにさん「簡易入力と単語帳の窓を続けて呼ぶと重なる。あとから呼んだ方の位置を
ずらす」).

The usual place is just below and right of the pointer. When the window already shown is in the
way, the other corners of the pointer come next, then the sides of that window, all kept inside
the work area of the pointer's monitor (moved up or left at its edges). If every place overlaps,
the one overlapping least is taken. Rectangles are (left, top, right, bottom) of the outer frames.
"""


def _inside(x, y, width, height, area, margin):
    wl, wt, wr, wb = area
    if x + width > wr:
        x = wr - width - margin
    if y + height > wb:
        y = wb - height - margin
    return int(max(wl, x)), int(max(wt, y))


def _overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


def near_pointer(pointer, size, area, avoid=(), offset=16, margin=8, gap=6):
    """Outer-frame (x, y) for a window of size (width, height)."""
    px, py = pointer
    width, height = size
    tries = [(px + offset, py + offset), (px - offset - width, py + offset),
             (px + offset, py - offset - height), (px - offset - width, py - offset - height)]
    for left, top, right, bottom in avoid:
        tries += [(right + gap, py + offset), (left - gap - width, py + offset),
                  (px + offset, bottom + gap), (px + offset, top - gap - height),
                  (right + gap, top), (left - gap - width, top),
                  (left, bottom + gap), (left, top - gap - height)]
    if avoid:
        # Last resort, where the other window is least in the way: the corners of the monitor
        wl, wt, wr, wb = area
        tries += [(wl, wt), (wr, wt), (wl, wb), (wr, wb)]
    best = None
    for x, y in tries:
        x, y = _inside(x, y, width, height, area, margin)
        rect = (x, y, x + width, y + height)
        covered = sum(_overlap(rect, other) for other in avoid)
        if covered == 0:
            return x, y
        if best is None or covered < best[0]:
            best = (covered, x, y)
    return best[1], best[2]


def outer_rect(window):
    """(left, top, right, bottom) of a shown tk window's outer frame, or None (hidden, minimized)."""
    try:
        if window is None or not window.winfo_exists() or not window.winfo_ismapped():
            return None
        if window.state() == 'iconic':
            return None
    except Exception:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(wintypes.HWND(int(window.wm_frame(), 16)), ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    try:
        x, y = window.winfo_x(), window.winfo_y()
        border = max(0, window.winfo_rootx() - x)
        title = max(0, window.winfo_rooty() - y)
        return x, y, x + window.winfo_width() + 2 * border, y + window.winfo_height() + title + border
    except Exception:
        return None
