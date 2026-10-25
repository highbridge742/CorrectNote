# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""The keys typed for each IME commit, for keystroke_doubt (2026-10-24 うにさん「ぜんぶ1.16に入れる」).

The memo's own KeyPress/KeyRelease (Tk bindings on that Text only: no global hook, no Win32 call) go to a
keystroke_doubt.StrokeClock; the times are time.perf_counter (Tk's %t moves in 15.6ms steps). Each commit takes
the keys typed for it and they ride on that commit's Occurrence (analysis_work), so they move with edits and go
with the reading. Nothing is written anywhere: the keys live in memory with the current text only.

`key_of_keycode` turns a Windows virtual key into the unshifted character of the JIS keyboard as
keyboard_layout names them; any other key is None (it still cuts the sequence in StrokeClock)."""
import time

_KEYS = {0xBA: ':', 0xBB: ';', 0xBC: ',', 0xBD: '-', 0xBE: '.', 0xBF: '/', 0xC0: '@', 0xDB: '[',
         0xDC: '¥', 0xDD: ']', 0xDE: '^', 0xE2: '\\'}
KEEP_MS = 2000.0          # keys left from no commit are dropped after this, while nothing is being converted


def key_of_keycode(keycode):
    if 0x41 <= keycode <= 0x5A:
        return chr(keycode + 32)
    if 0x30 <= keycode <= 0x39:
        return chr(keycode)
    return _KEYS.get(keycode)


class Strokes:
    """One clock for one Text (shift_slip.ShiftStrokeClock: the keys and the Shift presses).
    `for_commits(n)` hands them to exactly one commit, else to none."""

    def __init__(self):
        import shift_slip
        self.clock = shift_slip.ShiftStrokeClock(key_of_keycode)

    def install(self, widget):
        widget.bind('<KeyPress>', self._press, add=True)
        widget.bind('<KeyRelease>', self._release, add=True)

    def _press(self, event):
        try:
            self.clock.press(int(event.keycode))
        except Exception:
            pass

    def _release(self, event):
        try:
            self.clock.release(int(event.keycode))
        except Exception:
            pass

    def for_commits(self, count):
        """(keys, shifts) since the last commit when exactly one commit came now; with two or more nobody can
        tell which key went where, so ((), ()) (the correction then goes on without them)."""
        keys, shifts = self.clock.take()
        return (tuple(keys), tuple(shifts)) if count == 1 else ((), ())

    def idle(self, composing, now_ms=None):
        """No commit came: while nothing is being converted, keys older than KEEP_MS are not anyone's."""
        if composing:
            return
        now_ms = time.perf_counter() * 1000.0 if now_ms is None else now_ms
        self.clock.strokes = [s for s in self.clock.strokes if s[1] >= now_ms - KEEP_MS]
        self.clock.shifts = [s for s in self.clock.shifts if s[1] >= now_ms - KEEP_MS]
