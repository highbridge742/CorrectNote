# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
"""Colour emoji over a tk.Text on Windows (Notepad-like).

2026-10-13 うにさん「別のところからペーストすると絵文字は入るが、見た目に色が
付いていない。Windowsのメモ帳と同じ見た目にする」. Tk 8.6.9 draws text with
GDI, which has no colour fonts, so emoji come out in black. Each visible emoji
is drawn again with DirectWrite + Direct2D (D2D1_DRAW_TEXT_OPTIONS_ENABLE_COLOR_FONT)
into a GDI memory bitmap through ctypes (no COM apartment on the Tk thread), turned into a PhotoImage and laid over the
glyph as a small label. The text itself is not changed (no embedded images),
so indexes, analysis, undo and copying see the same characters as before.

Prototype and measurements: tools_local/v114_emoji/ (WORK.md)."""
import ctypes
import re
import sys

# Emoji drawn in colour. Characters outside these (e.g. 𠮷 and other CJK
# Extension characters, or ❤ without U+FE0F) keep Tk's own drawing, as in
# Notepad where they stay text-style.
_PRESENTATION_BMP = (
    '\u231a\u231b\u23e9-\u23ec\u23f0\u23f3\u25fd\u25fe\u2614\u2615'
    '\u2648-\u2653\u267f\u2693\u26a1\u26aa\u26ab\u26bd\u26be\u26c4\u26c5'
    '\u26ce\u26d4\u26ea\u26f2\u26f3\u26f5\u26fa\u26fd\u2705\u270a\u270b'
    '\u2728\u274c\u274e\u2753-\u2755\u2757\u2795-\u2797\u27b0\u27bf'
    '\u2b1b\u2b1c\u2b50\u2b55')
_BASE = ('(?:[\U0001F000-\U0001FAFF]|[' + _PRESENTATION_BMP + ']'
         '|[\u00a9\u00ae\u203c-\u3299]\ufe0f)')
_MODS = '[\ufe0f\u20e3\U0001F3FB-\U0001F3FF\U000E0020-\U000E007F]'
EMOJI = re.compile(
    '[\U0001F1E6-\U0001F1FF]{2}'                       # flags
    '|[0-9#*]\ufe0f?\u20e3'                            # keycaps
    '|' + _BASE + _MODS + '*(?:\u200d' + '(?:' + _BASE + '|[\u2000-\u3299])'
    + _MODS + '*)*')

POLL_MS = 90
# Variation selectors drawn as letters of their own. Tk 8.6.9 gives U+FE0F
# (and U+FE0E) a width of its own (18px at 10pt) and draws a BMP base such as
# ❤ with its text glyph, so ❤ + U+FE0F took two characters' room (2026-10-15 うにさん
# 「絵文字が2つ幅でした」). The selector is hidden (elide) and a pictograph
# base is drawn in the emoji font at its own size, so the colour lands in one
# emoji width like 😀. The text is unchanged: copying, analysis, undo and the
# cursor (text_edit's clusters) still see U+FE0F.
VS_TAG = 'correctnote_emoji_vs'
# Tk's own (black and white) glyph of an emoji the colour is laid over is
# drawn in the colour behind it, so the moment before a label is placed shows
# nothing instead of a black and white emoji (2026-10-15 うにさん: rows coming
# in at the top while scrolling). One tag per background colour.
HIDE_TAG = 'correctnote_emoji_hide_'
FONT_TAG = 'correctnote_emoji_font'
EMOJI_FAMILY = 'Segoe UI Emoji'
MAX_LABELS = 240        # a screen full of emoji still stays light


def emoji_spans(text):
    """[(start, end)] of the emoji drawn in colour, in Python indexes."""
    return [m.span() for m in EMOJI.finditer(text or '')]


_PAIR_COLUMNS = {}


def emoji_columns(widget):
    """How many `row.col` columns an emoji outside the BMP takes in this Tk.

    Tk 8.6.9 (Python 3.9) reads `row.col` with an emoji as one column, while
    Tk 8.6.12 and later (Python 3.11, which builds the released EXE) count its
    two UTF-16 halves (CI 2026-10-14: the colour was laid one character off
    per earlier emoji). Measured once per interpreter on a hidden pane."""
    key = id(widget.tk)
    if key not in _PAIR_COLUMNS:
        import tkinter as tk
        probe = tk.Text(widget)
        try:
            probe.insert('1.0', 'a\U0001F600b')
            _PAIR_COLUMNS[key] = 1 if probe.get('1.2') == 'b' else 2
        finally:
            probe.destroy()
    return _PAIR_COLUMNS[key]


def _units(text):
    return len(text.encode('utf-16-le')) // 2


if sys.platform == 'win32':
    from ctypes import wintypes as _wt

    class _GUID(ctypes.Structure):
        _fields_ = [('Data1', _wt.DWORD), ('Data2', _wt.WORD), ('Data3', _wt.WORD),
                    ('Data4', ctypes.c_ubyte * 8)]

        def __init__(self, text):
            import uuid
            u = uuid.UUID(text)
            super().__init__(u.time_low, u.time_mid, u.time_hi_version,
                             (ctypes.c_ubyte * 8)(*u.bytes[8:]))

    class _PIXEL_FORMAT(ctypes.Structure):
        _fields_ = [('format', ctypes.c_uint), ('alphaMode', ctypes.c_uint)]

    class _RT_PROPERTIES(ctypes.Structure):
        _fields_ = [('type', ctypes.c_uint), ('pixelFormat', _PIXEL_FORMAT),
                    ('dpiX', ctypes.c_float), ('dpiY', ctypes.c_float),
                    ('usage', ctypes.c_uint), ('minLevel', ctypes.c_uint)]

    class _COLOR_F(ctypes.Structure):
        _fields_ = [('r', ctypes.c_float), ('g', ctypes.c_float),
                    ('b', ctypes.c_float), ('a', ctypes.c_float)]

    class _RECT_F(ctypes.Structure):
        _fields_ = [('left', ctypes.c_float), ('top', ctypes.c_float),
                    ('right', ctypes.c_float), ('bottom', ctypes.c_float)]


def _method(obj, index, *argtypes, restype=ctypes.c_long):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return lambda *args: fn(obj, *args)


def _check(hr, what):
    if hr < 0:
        raise OSError('%s failed: 0x%08x' % (what, hr & 0xffffffff))


def _release(obj):
    if obj:
        _method(obj, 2, restype=ctypes.c_ulong)()


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


class EmojiRenderer:
    """DirectWrite + Direct2D drawing into a GDI memory bitmap (Windows only).

    No COM apartment is set up on the caller's thread: the Direct2D and
    DirectWrite factories are not COM-activated, and a DC render target
    replaces the WIC bitmap that needed CoInitializeEx on the Tk thread
    (CI 2026-10-14: an owned UIA request stopped finishing once the Tk thread
    had been put into a COM apartment)."""
    FAMILY = 'Segoe UI Emoji'

    def __init__(self):
        d2d1 = ctypes.WinDLL('d2d1')
        dwrite = ctypes.WinDLL('dwrite')
        self.gdi = ctypes.WinDLL('gdi32')
        self.gdi.CreateCompatibleDC.argtypes = [_wt.HDC]
        self.gdi.CreateCompatibleDC.restype = _wt.HDC
        self.gdi.CreateDIBSection.argtypes = [_wt.HDC, ctypes.c_void_p, ctypes.c_uint,
                                              ctypes.POINTER(ctypes.c_void_p), _wt.HANDLE,
                                              _wt.DWORD]
        self.gdi.CreateDIBSection.restype = _wt.HBITMAP
        self.gdi.SelectObject.argtypes = [_wt.HDC, _wt.HGDIOBJ]
        self.gdi.SelectObject.restype = _wt.HGDIOBJ
        self.gdi.DeleteObject.argtypes = [_wt.HGDIOBJ]
        self.gdi.DeleteDC.argtypes = [_wt.HDC]
        self.d2d = ctypes.c_void_p()
        d2d1.D2D1CreateFactory.argtypes = [ctypes.c_uint, ctypes.POINTER(_GUID),
                                           ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        _check(d2d1.D2D1CreateFactory(0, ctypes.byref(_GUID('06152247-6f50-465a-9245-118bfd3b6007')),
                                      None, ctypes.byref(self.d2d)), 'D2D1CreateFactory')
        self.dw = ctypes.c_void_p()
        dwrite.DWriteCreateFactory.argtypes = [ctypes.c_uint, ctypes.POINTER(_GUID),
                                               ctypes.POINTER(ctypes.c_void_p)]
        _check(dwrite.DWriteCreateFactory(0, ctypes.byref(_GUID('b859ee5a-d838-4b5b-a2e8-1adc7d93db48')),
                                          ctypes.byref(self.dw)), 'DWriteCreateFactory')
        # One DC render target, bound to a fresh memory bitmap per glyph.
        self.target = ctypes.c_void_p()
        props = _RT_PROPERTIES(0, _PIXEL_FORMAT(87, 3), 96.0, 96.0, 0, 0)   # B8G8R8A8, IGNORE
        _check(_method(self.d2d, 16, ctypes.POINTER(_RT_PROPERTIES),
                       ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(props), ctypes.byref(self.target)),
               'CreateDCRenderTarget')
        _method(self.target, 34, ctypes.c_uint, restype=None)(2)     # grayscale AA
        self.brush = ctypes.c_void_p()
        black = _COLOR_F(0, 0, 0, 1)
        _check(_method(self.target, 8, ctypes.POINTER(_COLOR_F), ctypes.c_void_p,
                       ctypes.POINTER(ctypes.c_void_p))(
                           ctypes.byref(black), None, ctypes.byref(self.brush)),
               'CreateSolidColorBrush')
        self._formats = {}

    def _format(self, px):
        fmt = self._formats.get(px)
        if fmt is None:
            fmt = ctypes.c_void_p()
            create = _method(self.dw, 15, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint,
                             ctypes.c_uint, ctypes.c_uint, ctypes.c_float, ctypes.c_wchar_p,
                             ctypes.POINTER(ctypes.c_void_p))
            _check(create(self.FAMILY, None, 400, 0, 5, float(px), 'ja-jp',
                          ctypes.byref(fmt)), 'CreateTextFormat')
            _method(fmt, 3, ctypes.c_uint)(2)       # SetTextAlignment(CENTER)
            _method(fmt, 4, ctypes.c_uint)(2)       # SetParagraphAlignment(CENTER)
            _method(fmt, 5, ctypes.c_uint)(1)       # SetWordWrapping(NO_WRAP)
            self._formats[px] = fmt
        return fmt

    def render(self, text, px, width, height, bg):
        """PPM bytes of `text` drawn in colour, centred on an opaque bg."""
        class _BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [('biSize', _wt.DWORD), ('biWidth', ctypes.c_long),
                        ('biHeight', ctypes.c_long), ('biPlanes', _wt.WORD),
                        ('biBitCount', _wt.WORD), ('biCompression', _wt.DWORD),
                        ('biSizeImage', _wt.DWORD), ('biXPelsPerMeter', ctypes.c_long),
                        ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', _wt.DWORD),
                        ('biClrImportant', _wt.DWORD)]
        header = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, 0,
                                   0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        dc = self.gdi.CreateCompatibleDC(None)
        if not dc:
            raise OSError('CreateCompatibleDC failed')
        bitmap = self.gdi.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        try:
            if not bitmap or not bits:
                raise OSError('CreateDIBSection failed')
            old = self.gdi.SelectObject(dc, bitmap)
            try:
                rect = _wt.RECT(0, 0, width, height)
                _check(_method(self.target, 57, _wt.HDC, ctypes.POINTER(_wt.RECT))(
                    dc, ctypes.byref(rect)), 'BindDC')
                _method(self.target, 48, restype=None)()                     # BeginDraw
                back = _COLOR_F(*_rgb(bg), 1.0)
                _method(self.target, 47, ctypes.POINTER(_COLOR_F), restype=None)(ctypes.byref(back))
                area = _RECT_F(0, 0, float(width), float(height))
                n = len(text.encode('utf-16-le')) // 2
                _method(self.target, 27, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p,
                        ctypes.POINTER(_RECT_F), ctypes.c_void_p, ctypes.c_uint,
                        ctypes.c_uint, restype=None)(
                            text, n, self._format(px), ctypes.byref(area), self.brush, 4, 0)
                _check(_method(self.target, 49, ctypes.c_void_p, ctypes.c_void_p)(None, None),
                       'EndDraw')
                ctypes.WinDLL('gdi32').GdiFlush()
                raw = ctypes.string_at(bits, width * height * 4)
            finally:
                self.gdi.SelectObject(dc, old)
        finally:
            if bitmap:
                self.gdi.DeleteObject(bitmap)
            self.gdi.DeleteDC(dc)
        rgb = bytearray(width * height * 3)
        rgb[0::3] = raw[2::4]
        rgb[1::3] = raw[1::4]
        rgb[2::3] = raw[0::4]
        return b'P6 %d %d 255' % (width, height) + bytes([10]) + bytes(rgb)


_RENDERER = None
_RENDERER_FAILED = False


def renderer():
    global _RENDERER, _RENDERER_FAILED
    if _RENDERER is None and not _RENDERER_FAILED:
        try:
            _RENDERER = EmojiRenderer()
        except Exception:
            _RENDERER_FAILED = True
    return _RENDERER


# Pointer events on a label go on to the pane under it. Modifiers travel in
# `state`, and double clicks are recognised by Tk from two forwarded presses:
# the press keeps its own `time` (without it event_generate sends a time of
# its own and a press on the pane plus one on a label never make a double).
_FORWARD = ('<ButtonPress>', '<ButtonRelease>', '<Motion>', '<MouseWheel>')


class EmojiOverlay:
    """Keeps colour labels over the emoji visible in one tk.Text."""

    def __init__(self, widget, render):
        self.w = widget
        self.r = render
        self.images = {}
        self._rgb = {}
        self._direct = {}
        self._tags = set()
        self._view = None
        self._repaint_job = None
        self._repaint_cols = None
        self._flush = False
        self._hidden = None         # what _hide_glyphs last tagged
        self._hide_tags = set()
        self._failed = False        # colour drawing failed: hide nothing
        self._skipped = set()       # (row, col) of visible emoji left without a label
        self.labels = []
        self.shown = []
        self.idle = None
        self.poll = None
        self.stopped = False
        for seq in ('<Configure>', '<KeyRelease>', '<ButtonRelease-1>', '<MouseWheel>',
                    '<B1-Motion>', '<FocusIn>', '<FocusOut>', '<<Selection>>'):
            widget.bind(seq, self.schedule, add=True)
        widget.bind('<Destroy>', self._stop, add=True)
        # Follow every edit, cursor move and scroll at once, not only keys:
        # a reflowed (wrapped) row must not show a label over the old place.
        try:
            from analysis_work import observe_text
            observe_text(widget)
            observers = widget._correctnote_observers
            for name in ('moved', 'viewed', 'scrolled', 'tagged'):
                observers.setdefault(name, []).append(self.schedule)
            # Right after the pane's yview/see/tag command, before Tk redraws.
            for name in ('viewed', 'scrolled', 'tagged'):
                observers[name].insert(0, self._before_redraw)
            # A new emoji (typed, pasted, Win+.) and rows a jump brings in are
            # hidden before Tk draws them.
            observers.setdefault('changed', []).insert(0, lambda args=None: self._hide_glyphs())
            for name in ('viewed', 'scrolled'):
                observers.setdefault(name, []).insert(0, self._hide_glyphs)
            observers.setdefault('changed', []).append(lambda args=None: self.schedule())
        except Exception:
            pass
        self._tick()

    def _stop(self, event=None):
        """The pane is going away: no timer may outlive it."""
        if event is not None and event.widget is not self.w:
            return
        for job in (self.poll, self.idle, self._repaint_job):
            if job is not None:
                try:
                    self.w.after_cancel(job)
                except Exception:
                    pass
        self.poll = self.idle = self._repaint_job = None
        self.stopped = True

    def _tick(self):
        self.poll = None
        if self.stopped:
            return
        try:
            if not self.w.winfo_exists():
                return
            self._flush = True
            self.refresh()
        except Exception:
            pass
        finally:
            self._flush = False
        try:
            self.poll = self.w.after(POLL_MS, self._tick)
        except Exception:
            self.poll = None

    def schedule(self, event=None):
        if self.idle is None and not self.stopped:
            try:
                self.idle = self.w.after_idle(self._idle)
            except Exception:
                self.idle = None

    def _idle(self):
        self.idle = None
        try:
            if self.w.winfo_exists():
                self._flush = True
                self.refresh()
        except Exception:
            pass
        finally:
            self._flush = False

    def _call(self, *args):
        """Read-only text commands straight to Tk. The app wraps the pane's
        command in Python (analysis_work.observe_text); a screen of emoji
        asks for ~5 values each, and the wrapper made that 3x slower."""
        w = self.w
        name = w._w + '_correctnote_work'
        if name not in self._direct:
            self._direct[name] = bool(w.tk.call('info', 'commands', name))
        return w.tk.call(name if self._direct[name] else w._w, *args)

    def _background(self, tags, focused, colors):
        bg = colors['']
        for tag in tags:
            if str(tag).startswith('cn_paper_'):
                continue    # 文字の裏の絵（appearance.Paper）は、絵文字の箱の地にしない
            value = colors.get(tag)
            if value is None:
                if tag == 'sel':
                    value = (str(self._call('tag', 'cget', 'sel', '-background')) if focused
                             else str(self._call('cget', '-inactiveselectbackground')))
                else:
                    value = str(self._call('tag', 'cget', tag, '-background'))
                colors[tag] = value
            if value:
                bg = value
        return bg

    def _hex(self, color):
        value = self._rgb.get(color)
        if value is None:
            r, g, b = self.w.winfo_rgb(color)
            value = self._rgb[color] = '#%02x%02x%02x' % (r >> 8, g >> 8, b >> 8)
        return value

    def _image(self, text, width, height, bg):
        key = (text, width, height, bg)
        img = self.images.get(key)
        if img is None:
            if len(self.images) > 400:
                self.images.clear()
            px = max(8, round(min(width + 2, height) * 0.78))
            img = self.images[key] = __import__('tkinter').PhotoImage(
                master=self.w, data=self.r.render(text, px, width, height, bg))
        return img

    def _narrow(self, text, line0, lead, width_of):
        """Hide the visible variation selectors and the later parts of a joined
        emoji (👨‍👩‍👧: Tk gives each part its own width; the colour draws the
        whole family in the first one's room). A pictograph base before U+FE0F
        is drawn in the emoji font (see VS_TAG), and so is an emoji outside the
        BMP: Tk picks its own fallback font for those, and the one Tk 8.6.12+
        picks (Python 3.11, the released EXE) is narrower or wider than the emoji
        font ❤ is drawn in (CI 2026-10-16: ❤️ 5px off 😀). With both in the
        emoji font they take the same room in every Tk. Only the screen's rows."""
        astral = any(ord(ch) > 0xffff for ch in text)
        if ('\ufe0f' not in text and '\ufe0e' not in text and '\u200d' not in text
                and not astral):
            return
        call = self._call
        if VS_TAG not in self._tags:
            call('tag', 'configure', VS_TAG, '-elide', 1)
            self._tags.add(VS_TAG)
        for offset, line in enumerate(text.split('\n')):
            if ('\ufe0f' not in line and '\ufe0e' not in line and '\u200d' not in line
                    and not any(ord(ch) > 0xffff for ch in line)):
                continue
            row = line0 + offset
            base = lead if offset == 0 else 0
            hide = {i for i, ch in enumerate(line) if ch in '\ufe0e\ufe0f'}
            bases = {}
            for start, end in emoji_spans(line):
                if '\u200d' in line[start:end]:
                    hide.update(range(start + 1, end))
                if ord(line[start]) > 0xffff:
                    # The whole emoji: a skin tone left in the letters' font sat
                    # at another height and the colour was not placed (👍🏽).
                    bases[start] = end
                elif (line[start + 1:start + 2] == '\ufe0f'
                        and line[start] not in '0123456789#*'):
                    bases[start] = start + 1
            for i in sorted(hide):
                index = '%d.%d' % (row, base + width_of(line[:i]))
                if VS_TAG not in self.w.tk.splitlist(call('tag', 'names', index)):
                    call('tag', 'add', VS_TAG, index)
            for start, end in bases.items():
                # Columns of the whole emoji: an emoji outside the BMP is one
                # column in Tk 8.6.9, two (UTF-16) later.
                self._emoji_font('%d.%d' % (row, base + width_of(line[:start])),
                                 '%d.%d' % (row, base + width_of(line[:end])))

    def _emoji_font(self, index, end=None):
        call = self._call
        tags = self.w.tk.splitlist(call('tag', 'names', index))
        have = [str(tag) for tag in tags if str(tag).startswith(FONT_TAG)]
        # The size follows the letters around it: the font the base would have
        # without this tag. It is looked at every time, so the shrunken view
        # (右クリック2回) and back take ❤ along (2026-10-15 うにさん「縮小モードで
        # ❤️ が縮小されません」: the tag kept the size it was first given).
        font = ''
        for tag in reversed(tags):      # highest priority first
            if str(tag).startswith(FONT_TAG):
                continue
            font = str(call('tag', 'cget', tag, '-font'))
            if font:
                break
        if not font:
            font = str(call('cget', '-font'))
        try:
            size = int(self.w.tk.call('font', 'actual', font, '-size'))
        except Exception:
            return
        name = FONT_TAG + str(size).replace('-', 'px')
        if have == [name]:
            return
        span = (index,) if end is None else (index, end)
        for old in have:
            call('tag', 'remove', old, *span)
        if name not in self._tags:
            call('tag', 'configure', name, '-font', '{%s} %d' % (EMOJI_FAMILY, size))
            self._tags.add(name)
        # Above the part-of-speech fonts (made earlier and later).
        call('tag', 'raise', name)
        call('tag', 'add', name, *span)

    def placements(self):
        """[(x, y, w, h, text, bg)] for the emoji visible now."""
        w = self.w
        if not w.winfo_ismapped():
            return []
        call = self._call
        # Only the characters on screen: a pasted row can be tens of
        # thousands of characters long (tests_gui_encoded_paste).
        # Tk 8.6.9 writes the indexes it returns with an emoji counted as two
        # columns, but reads 'row.col' with it counted as one. So the screen
        # corners go to `get` as '@x,y' themselves, never as returned indexes.
        first = '@0,0'
        last = '@%d,%d' % (w.winfo_width(), w.winfo_height())
        line0 = int(str(call('index', first)).split('.')[0])
        text = str(call('get', first, last)) + str(call('get', last))
        if not EMOJI.search(text):
            return []
        # Column of a Python offset: Tk 8.6.9 counts an emoji as one column,
        # later Tk as two (emoji_columns).
        width_of = len if emoji_columns(w) == 1 else _units
        # Column of the first visible character within its row.
        lead = width_of(str(call('get', '%d.0' % line0, first)))
        self._narrow(text, line0, lead, width_of)
        focused = w.focus_get() is w
        colors = {'': str(call('cget', '-bg'))}
        out = []
        skipped = self._skipped = set()   # visible emoji without a label
        for offset, line in enumerate(text.split('\n')):
            row = line0 + offset
            base = lead if offset == 0 else 0
            for start, end in emoji_spans(line):
                first_col = base + width_of(line[:start])
                last_col = base + width_of(line[:end - 1])
                a = w.tk.splitlist(call('bbox', '%d.%d' % (row, first_col)))
                b = a if last_col == first_col else w.tk.splitlist(
                    call('bbox', '%d.%d' % (row, last_col)))
                if len(b) != 4 or int(b[2]) == 0:
                    # A hidden selector last (VS_TAG): its empty box sits a
                    # pixel or two off the base's top when the row's fonts
                    # differ (❤ in the emoji font, the letters after it in a
                    # part-of-speech font), and ❤️ was left without colour
                    # while its own glyph was hidden (2026-10-15). Measured by
                    # the base and the next letter instead.
                    b = a
                if len(a) != 4 or int(a[1]) != int(b[1]):
                    skipped.add((row, first_col))
                    continue
                x, y, h = int(a[0]), int(a[1]), int(a[3])
                width = int(b[0]) + int(b[2]) - x
                # The cluster ends where the next character starts. Tk draws a
                # skin tone with no width and reports the box of the letter
                # after it, which laid the colour over that letter and hid the
                # cursor between them (2026-10-15, 👍🏽 then b).
                c = w.tk.splitlist(call('bbox', '%d.%d' % (row, base + width_of(line[:end]))))
                # On the same display line (fonts may put its top elsewhere).
                if (len(c) == 4 and int(c[1]) < y + h and int(c[1]) + int(c[3]) > y
                        and int(c[0]) > x):
                    width = int(c[0]) - x
                if width < 4 or h < 4:
                    skipped.add((row, first_col))
                    continue
                tags = w.tk.splitlist(call('tag', 'names', '%d.%d' % (row, first_col)))
                # Leave the insertion cursor's pixels at both edges visible.
                out.append((x + 1, y, width - 2, h, line[start:end],
                            self._hex(self._background(tags, focused, colors))))
                if len(out) >= MAX_LABELS:
                    return out
        return out

    def _view_moved(self):
        # Where the first row sits on screen, not yview's fractions: Tk keeps
        # refining those while it measures rows in the background, with
        # nothing moving (each poll then drew the pane again for nothing).
        try:
            line = self.w.tk.splitlist(self._call('dlineinfo', '@0,0'))
            view = (str(self._call('index', '@0,0')), str(line[1]) if len(line) > 1 else '',
                    str(self._call('xview')))
        except Exception:
            return False
        moved, self._view = view != self._view, view
        return moved

    def _repaint(self, cols, later=True):
        """Draw the pane's text again under the label columns (an Expose).

        Tk moves rows by copying their pixels: when it scrolls, and when a row
        above changes height (part-of-speech fonts, ❤ drawn in the emoji
        font). The copy takes the colour labels' pixels along, and a second
        row of emoji stayed above or below the real one until something drew
        over it (2026-10-15 うにさん「スクロール時に絵文字が変です」; the copy was
        there before 2026-10-15 too). The labels are child windows and stay on
        top. Once more a little later, for a copy Tk makes after this refresh."""
        w = self.w
        x0, x1 = max(0, int(cols[0])), min(w.winfo_width(), int(cols[1]))
        if x1 > x0:
            try:
                w.event_generate('<Expose>', x=x0, y=0, width=x1 - x0, height=w.winfo_height())
                if self._flush:
                    # Now, in this turn: during a wheel glide the next step
                    # (a timer) came before Tk's own redraw, so a copy was on
                    # screen all along the glide (うにさん「だめでした」). Only
                    # from the overlay's own idle/timer turn, never inside a
                    # caller's command.
                    w.update_idletasks()
            except Exception:
                pass
        if later and not self.stopped:
            pending = self._repaint_cols
            self._repaint_cols = cols if pending is None else (
                min(pending[0], cols[0]), max(pending[1], cols[1]))
            if self._repaint_job is None:
                try:
                    self._repaint_job = w.after(60, self._repaint_later)
                except Exception:
                    self._repaint_job = None

    def _before_redraw(self, *args):
        """Have Tk draw the label columns again instead of copying them.

        Tk moves rows by copying their pixels (scrolling, a row above
        growing), and the copy took the colour labels along: for an instant at
        every scroll a second row of emoji showed (2026-10-15 うにさん
        「スクロールした瞬間だけです」). Marked before Tk redraws, those rows are
        drawn afresh, so nothing of a label is copied; the labels are laid
        again in the same turn (refresh, _repaint)."""
        if self.stopped or not self.shown:
            return
        cols = self._columns(self.shown)
        w = self.w
        try:
            x0, x1 = max(0, int(cols[0])), min(w.winfo_width(), int(cols[1]))
            if x1 > x0:
                w.event_generate('<Expose>', x=x0, y=0, width=x1 - x0, height=w.winfo_height())
        except Exception:
            pass

    def _repaint_later(self):
        self._repaint_job = None
        cols, self._repaint_cols = self._repaint_cols, None
        if cols is not None and not self.stopped:
            self._flush = True
            try:
                self._repaint(cols, later=False)
            finally:
                self._flush = False

    @staticmethod
    def _columns(*groups):
        spans = [(p[0] - 2, p[0] + p[2] + 2) for group in groups for p in group]
        return (min(a for a, _ in spans), max(b for _, b in spans)) if spans else None

    def _hide_glyphs(self):
        """Tag the emoji the colour is laid over, on screen and one screen
        above and below, so Tk draws its own glyph in the background colour
        (HIDE_TAG). Rows that scroll in are tagged already; a jump is tagged
        before Tk draws (called from the pane's yview/see and edits)."""
        if self.stopped or self._failed:
            return
        w = self.w
        call = self._call
        try:
            # About one screen above and below, counted in characters: as many
            # as are on screen. Not rows (a pasted row can be tens of thousands
            # of characters long, tests_gui_encoded_paste) and not display
            # lines (Tk 8.6.9 took 9 s to count them in such a row).
            height = max(1, w.winfo_height())
            corner = '@%d,%d' % (w.winfo_width(), height)
            span = max(200, len(str(call('get', '@0,0', corner))))
            # Expressions, not the row.col Tk returns (Tk 8.6.9 reads those
            # back one column off after an emoji); only the rows are taken.
            a = '@0,0 -%dc' % span
            b = '%s +%dc' % (corner, span)
            first = int(str(call('index', a)).split('.')[0])
            last = int(str(call('index', b)).split('.')[0])
            text = str(call('get', a, b))
            width_of = len if emoji_columns(w) == 1 else _units
            lead = width_of(str(call('get', '%d.0' % first, a)))
            focused = w.focus_get() is w
            colors = {'': str(call('cget', '-bg'))}
            ranges = []
            if EMOJI.search(text):
                for offset, line in enumerate(text.split('\n')):
                    row = first + offset
                    base = lead if offset == 0 else 0
                    for start, end in emoji_spans(line):
                        c0, c1 = base + width_of(line[:start]), base + width_of(line[:end])
                        if (row, c0) in self._skipped:
                            # No label could be placed: Tk's own glyph stays.
                            continue
                        tags = w.tk.splitlist(call('tag', 'names', '%d.%d' % (row, c0)))
                        tags = [t for t in tags if not str(t).startswith(HIDE_TAG)]
                        ranges.append((row, c0, c1, self._hex(self._background(tags, focused, colors))))
            sel = self._hex(str(call('tag', 'cget', 'sel', '-background')) or colors[''])
            mark = (first, last, tuple(ranges), sel)
            if mark == self._hidden:
                return
            self._hidden = mark
            for tag in self._hide_tags:
                call('tag', 'remove', tag, a, b)
            for row, c0, c1, bg in ranges:
                tag = HIDE_TAG + bg.lstrip('#')
                if tag not in self._hide_tags:
                    self._hide_tags.add(tag)
                call('tag', 'configure', tag, '-foreground', bg, '-selectforeground', sel)
                call('tag', 'add', tag, '%d.%d' % (row, c0), '%d.%d' % (row, c1))
            for tag in self._hide_tags:
                call('tag', 'raise', tag)     # above the part-of-speech colours and sel
        except Exception:
            pass

    def _unhide_all(self):
        for tag in self._hide_tags:
            try:
                self._call('tag', 'remove', tag, '1.0', 'end')
            except Exception:
                pass
        self._hidden = None

    def refresh(self):
        before = set(self._skipped)
        self._hide_glyphs()
        found = self.placements()
        if self._skipped != before:
            # An emoji left without a label keeps Tk's own glyph.
            self._hidden = None
            self._hide_glyphs()
        moved = self._view_moved()
        if found == self.shown:
            if moved and found:
                self._repaint(self._columns(found))
            return
        old = self.shown
        import tkinter as tk
        for i, (x, y, width, h, text, bg) in enumerate(found):
            if i < len(self.labels):
                label = self.labels[i]
            else:
                label = tk.Label(self.w, bd=0, highlightthickness=0, padx=0, pady=0,
                                 cursor=str(self.w.cget('cursor')) or 'xterm',
                                 takefocus=0)
                for seq in _FORWARD:
                    label.bind(seq, lambda e, s=seq: self._forward(e, s))
                self.labels.append(label)
            if i < len(self.shown) and self.shown[i] == found[i]:
                continue
            try:
                label.configure(image=self._image(text, width, h, bg))
            except Exception:
                # No colour after all: Tk's own glyphs must show.
                self._failed = True
                self._unhide_all()
                raise
            # bbox is measured from the window's outer edge; place would
            # otherwise start inside the pane's padding.
            label.place(x=x, y=y, width=width, height=h, bordermode='outside')
        for label in self.labels[len(found):]:
            label.place_forget()
        self.shown = found
        cols = self._columns(old, found)
        if cols is not None:
            self._repaint(cols)

    def _forward(self, event, seq):
        w = self.w
        options = dict(x=event.x_root - w.winfo_rootx(), y=event.y_root - w.winfo_rooty(),
                       rootx=event.x_root, rooty=event.y_root, state=event.state)
        try:
            options['time'] = int(event.time)
        except Exception:
            pass
        if seq == '<MouseWheel>':
            options['delta'] = event.delta
        elif seq in ('<ButtonPress>', '<ButtonRelease>'):
            seq = '<%s-%s>' % (seq[1:-1], event.num)
            if seq == '<ButtonPress-1>':
                w.focus_set()
        try:
            w.event_generate(seq, **options)
        except Exception:
            pass
        return 'break'


def install(widget):
    """Lay colour emoji over `widget` (a tk.Text). Windows only; quietly
    does nothing where Direct2D is not available."""
    if sys.platform != 'win32':
        return None
    existing = getattr(widget, '_correctnote_emoji_color', None)
    if existing is not None:
        return existing
    render = renderer()
    if render is None:
        return None
    overlay = EmojiOverlay(widget, render)
    widget._correctnote_emoji_color = overlay
    return overlay
