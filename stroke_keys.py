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


# 字でないキーの種類（2026-11-22 うにさん「再入力変換は、実際にどのキーを押したかという情報から、平仮名にしてください」・
# 打鍵の記録で変換の Space と BackSpace が見分けられなかった）。記録の字は前と同じ空の字のまま（読む所は全部「空の字＝字で
# ないキー」として扱うので、答えは変わらない）で、種類の名前だけを足す（NonChar.name）。子のプロセスへ渡す時（pickle）は
# ただの空の字になるので、補正の答えも控えも前と同じ。読むのは typed_kana（再入力変換）だけ。CN_STROKE_KEY_KINDS=0 で前の形
KIND_OF_KEYCODE = {8: 'BackSpace', 9: 'Tab', 13: 'Return', 27: 'Escape', 32: 'space', 33: 'Prior', 34: 'Next', 35: 'End',
                   36: 'Home', 37: 'Left', 38: 'Up', 39: 'Right', 40: 'Down', 46: 'Delete', 0x1C: 'Convert',
                   0x1D: 'NonConvert', 0x75: 'F6', 0x76: 'F7', 0x77: 'F8', 0x78: 'F9', 0x79: 'F10',
                   0xF3: 'Zenkaku_Hankaku', 0xF4: 'Zenkaku_Hankaku'}


class NonChar(str):
    """字でないキーの記録。値は空の字（'' と等しく、偽）。name に種類（BackSpace・space など。知らないキーは 'other'）。"""

    def __new__(cls, name):
        self = str.__new__(cls, '')
        self.name = name
        return self

    def __reduce__(self):
        return (str, ('',))

    def __reduce_ex__(self, protocol):
        return (str, ('',))


def kind_of_keycode(keycode):
    return KIND_OF_KEYCODE.get(keycode, 'other')


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
            keycode = int(event.keycode)
            strokes = self.clock.strokes
            before = len(strokes)
            self.clock.release(keycode)
            if (len(self.clock.strokes) == before + 1 and self.clock.strokes[-1][0] == ''
                    and not isinstance(self.clock.strokes[-1][0], NonChar)
                    and __import__('os').environ.get('CN_STROKE_KEY_KINDS') != '0'):
                at = self.clock.strokes[-1][1]
                self.clock.strokes[-1] = (NonChar(kind_of_keycode(keycode)), at)
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
