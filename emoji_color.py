# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
"""Colour emoji over a tk.Text on Windows (Notepad-like).

2026-10-13 うにさん「別のところからペーストすると絵文字は入るが、見た目に色が
付いていない。Windowsのメモ帳と同じ見た目にする」. Tk 8.6.9 draws text with
GDI, which has no colour fonts, so emoji come out in black. Each visible emoji
is drawn again with DirectWrite + Direct2D (D2D1_DRAW_TEXT_OPTIONS_ENABLE_COLOR_FONT)
into a WIC bitmap through ctypes, turned into a PhotoImage and laid over the
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
MAX_LABELS = 240        # a screen full of emoji still stays light


def emoji_spans(text):
    """[(start, end)] of the emoji drawn in colour, in Python indexes."""
    return [m.span() for m in EMOJI.finditer(text or '')]


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
    """DirectWrite + Direct2D + WIC, created once (Windows only)."""
    FAMILY = 'Segoe UI Emoji'

    def __init__(self):
        ole32 = ctypes.WinDLL('ole32')
        ole32.CoInitializeEx(None, 2)
        d2d1 = ctypes.WinDLL('d2d1')
        dwrite = ctypes.WinDLL('dwrite')
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
        self.wic = ctypes.c_void_p()
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, _wt.DWORD,
                                           ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        _check(ole32.CoCreateInstance(ctypes.byref(_GUID('cacaf262-9370-4615-a13b-9f5539da4c0a')),
                                      None, 1,
                                      ctypes.byref(_GUID('ec5ec8a9-c395-4314-9c77-54d7a935ff70')),
                                      ctypes.byref(self.wic)), 'WIC factory')
        self._pbgra = _GUID('6fddc324-4e03-4bfe-b185-3d77768dc910')
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
        bitmap, target, brush = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            _check(_method(self.wic, 17, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(_GUID),
                           ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(
                               width, height, ctypes.byref(self._pbgra), 1,
                               ctypes.byref(bitmap)), 'CreateBitmap')
            props = _RT_PROPERTIES(0, _PIXEL_FORMAT(87, 1), 96.0, 96.0, 0, 0)
            _check(_method(self.d2d, 13, ctypes.c_void_p, ctypes.POINTER(_RT_PROPERTIES),
                           ctypes.POINTER(ctypes.c_void_p))(
                               bitmap, ctypes.byref(props), ctypes.byref(target)),
                   'CreateWicBitmapRenderTarget')
            black = _COLOR_F(0, 0, 0, 1)
            _check(_method(target, 8, ctypes.POINTER(_COLOR_F), ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_void_p))(
                               ctypes.byref(black), None, ctypes.byref(brush)),
                   'CreateSolidColorBrush')
            _method(target, 34, ctypes.c_uint, restype=None)(2)     # grayscale AA
            _method(target, 48, restype=None)()                     # BeginDraw
            back = _COLOR_F(*_rgb(bg), 1.0)
            _method(target, 47, ctypes.POINTER(_COLOR_F), restype=None)(ctypes.byref(back))
            rect = _RECT_F(0, 0, float(width), float(height))
            n = len(text.encode('utf-16-le')) // 2
            _method(target, 27, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p,
                    ctypes.POINTER(_RECT_F), ctypes.c_void_p, ctypes.c_uint,
                    ctypes.c_uint, restype=None)(
                        text, n, self._format(px), ctypes.byref(rect), brush, 4, 0)
            _check(_method(target, 49, ctypes.c_void_p, ctypes.c_void_p)(None, None),
                   'EndDraw')
            stride = width * 4
            buf = (ctypes.c_ubyte * (stride * height))()
            _check(_method(bitmap, 7, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                           ctypes.c_void_p)(None, stride, len(buf), buf), 'CopyPixels')
        finally:
            _release(brush)
            _release(target)
            _release(bitmap)
        raw = bytes(buf)
        rgb = bytearray(width * height * 3)
        rgb[0::3] = raw[2::4]
        rgb[1::3] = raw[1::4]
        rgb[2::3] = raw[0::4]
        return b'P6 %d %d 255\n' % (width, height) + bytes(rgb)


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
# `state`, and double clicks are recognised by Tk from two forwarded presses.
_FORWARD = ('<ButtonPress>', '<ButtonRelease>', '<Motion>', '<MouseWheel>')


class EmojiOverlay:
    """Keeps colour labels over the emoji visible in one tk.Text."""

    def __init__(self, widget, render):
        self.w = widget
        self.r = render
        self.images = {}
        self._rgb = {}
        self._direct = {}
        self.labels = []
        self.shown = []
        self.idle = None
        self.poll = None
        self.stopped = False
        for seq in ('<Configure>', '<KeyRelease>', '<ButtonRelease-1>', '<MouseWheel>',
                    '<B1-Motion>', '<FocusIn>', '<FocusOut>', '<<Selection>>'):
            widget.bind(seq, self.schedule, add=True)
        widget.bind('<Destroy>', self._stop, add=True)
        self._tick()

    def _stop(self, event=None):
        """The pane is going away: no timer may outlive it."""
        if event is not None and event.widget is not self.w:
            return
        for job in (self.poll, self.idle):
            if job is not None:
                try:
                    self.w.after_cancel(job)
                except Exception:
                    pass
        self.poll = self.idle = None
        self.stopped = True

    def _tick(self):
        self.poll = None
        if self.stopped:
            return
        try:
            if not self.w.winfo_exists():
                return
            self.refresh()
        except Exception:
            pass
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
                self.refresh()
        except Exception:
            pass

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
        # Python offset (= Tk input column) of the first visible character.
        lead = len(str(call('get', '%d.0' % line0, first)))
        focused = w.focus_get() is w
        colors = {'': str(call('cget', '-bg'))}
        out = []
        for offset, line in enumerate(text.split('\n')):
            row = line0 + offset
            base = lead if offset == 0 else 0
            for start, end in ((a + base, b + base) for a, b in emoji_spans(line)):
                # An emoji is one index column in Tk 8.6.9 ('.end' alone
                # counts it twice), so Python offsets are Tk columns.
                a = w.tk.splitlist(call('bbox', '%d.%d' % (row, start)))
                b = a if end - start == 1 else w.tk.splitlist(
                    call('bbox', '%d.%d' % (row, end - 1)))
                if len(a) != 4 or len(b) != 4 or int(a[1]) != int(b[1]):
                    continue
                x, y, h = int(a[0]), int(a[1]), int(a[3])
                width = int(b[0]) + int(b[2]) - x
                if width < 4 or h < 4:
                    continue
                tags = w.tk.splitlist(call('tag', 'names', '%d.%d' % (row, start)))
                # Leave the insertion cursor's pixels at both edges visible.
                out.append((x + 1, y, width - 2, h, line[start - base:end - base],
                            self._hex(self._background(tags, focused, colors))))
                if len(out) >= MAX_LABELS:
                    return out
        return out

    def refresh(self):
        found = self.placements()
        if found == self.shown:
            return
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
            label.configure(image=self._image(text, width, h, bg))
            # bbox is measured from the window's outer edge; place would
            # otherwise start inside the pane's padding.
            label.place(x=x, y=y, width=width, height=h, bordermode='outside')
        for label in self.labels[len(found):]:
            label.place_forget()
        self.shown = found

    def _forward(self, event, seq):
        w = self.w
        options = dict(x=event.x_root - w.winfo_rootx(), y=event.y_root - w.winfo_rooty(),
                       rootx=event.x_root, rooty=event.y_root, state=event.state)
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
