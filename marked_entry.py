# -*- coding: utf-8 -*-
"""One-line native Entry with visible tab/newline marks and an exact raw value."""
import tkinter as tk
from tkinter import font as tkfont


# Keep native Tcl errors in Tcl. The raw value and visible value use the
# same character indices, including this Tk's own supplementary characters.
_COMMAND = r'''
namespace eval ::correctnote {}
proc ::correctnote::MarkedEntry {native value guard command args} {
    if {$command eq "get" && [llength $args] == 0} {
        return [set $value]
    }
    set edit 0
    if {$command eq "insert" && [llength $args] == 2} {
        set before [$native get]
        set first [$native index [lindex $args 0]]
        set last $first
        set inserted [lindex $args 1]
        set shown $inserted
        if {[info exists ::correctnote::emoji_blank] && $::correctnote::emoji_blank} {
            set shown [regsub -all {[\ud83c-\ud83e][\udc00-\udfff]} $shown "\u3000\u2009"]
            set shown [regsub -all {[\u2190-\u2bff]\ufe0f} $shown "\u3000\u2009"]
        }
        set shown [string map [list "\t" "\u2003" "\n" "\u21b5" "\r" "\u21b5" "\ufe0f" "\u200b" "\ufe0e" "\u200b"] $shown]
        set result [$native insert $first $shown]
        set edit 1
    } elseif {$command eq "delete" && [llength $args] in {1 2}} {
        set before [$native get]
        set first [$native index [lindex $args 0]]
        set last [expr {$first + 1}]
        if {[llength $args] == 2} {set last [$native index [lindex $args 1]]}
        set inserted ""
        set result [$native delete {*}$args]
        set edit 1
    } else {
        return [$native $command {*}$args]
    }
    if {$edit && [$native get] ne $before} {
        set raw [set $value]
        set $guard 1
        try {
            set $value [string range $raw 0 [expr {$first - 1}]]$inserted[string range $raw $last end]
        } finally {
            set $guard 0
        }
    }
    return $result
}
'''


import re as _re
# Emoji whose colour is laid over the field (marked_entry._paint_emoji):
# shown as blank space of the same length (U+1F000–U+1FBFF, and a BMP
# pictograph with U+FE0F). Only while Direct2D draws the colour.
_BLANK_ASTRAL = _re.compile('[\U0001F000-\U0001FBFF]')
_BLANK_SELECTED = _re.compile('[\u2190-\u2bff]\ufe0f')
_EMOJI_BLANK = [False]


class MarkedEntry(tk.Entry):
    """Store real control characters; paint marks without changing that value.

    Literal ↵ and em spaces typed by the user remain those literal characters.
    Native insertion/deletion, selection and clipboard bindings keep operating
    in the original Entry's coordinates. No polling or application Text proxy.
    """
    def __init__(self, master, *, textvariable, tab_colors, **kwargs):
        self.value = textvariable
        try:
            import emoji_color
            _EMOJI_BLANK[0] = emoji_color.renderer() is not None
        except Exception:
            _EMOJI_BLANK[0] = False
        self._display = tk.StringVar(master, value=self._show(textvariable.get()))
        self._guard = tk.BooleanVar(master, value=False)
        self._tab_colors = tab_colors
        self._paint_job = None
        self._marks = []
        self._emoji = []            # colour labels over emoji (emoji_color)
        self._emoji_images = {}
        super().__init__(master, textvariable=self._display, **kwargs)
        self._native = self._w + '_marked_native'
        self.tk.eval(_COMMAND)
        self.tk.setvar('::correctnote::emoji_blank', int(_EMOJI_BLANK[0]))
        self.tk.call('rename', self._w, self._native)
        self.tk.call('interp', 'alias', '', self._w, '',
                     '::correctnote::MarkedEntry', self._native,
                     '::' + str(self.value).lstrip(':'), '::' + str(self._guard).lstrip(':'))
        self._value_trace = self.value.trace_add('write', self._value_changed)
        self._font = tkfont.Font(self, font=self.cget('font'))
        self._font_spec = self.cget('font')
        self._wide_units = int(self.tk.call('string', 'length', '😀'))
        self.configure(xscrollcommand=lambda *_: self._schedule_paint())
        for event in ('<Configure>', '<KeyRelease>', '<ButtonRelease-1>',
                      '<B1-Motion>', '<FocusIn>', '<FocusOut>'):
            self.bind(event, self._schedule_paint, add=True)
        self.bind('<Destroy>', self._destroyed, add=True)
        self._schedule_paint()

    @staticmethod
    def _show(value):
        # U+FE0F/FE0E have a width of their own in Tk 8.6.9 and showed as a
        # blank after ❤ (2026-10-15 うにさん「検索窓に貼ると空白がついて来ます」); shown
        # as a zero-width space, one character for one, so the indices and
        # the raw value (searching, copying) keep the selector.
        if _EMOJI_BLANK[0]:
            # Colour is drawn over these (emoji_color): Tk's own black and
            # white glyph is not shown at all, even for the moment before
            # the colour is placed (2026-10-15 うにさん「検索ウインドウで、色のない絵文字が
            # 見えます」). The same length in Tk's characters, so indices stay.
            value = _BLANK_ASTRAL.sub('\u3000\u2009', value)
            value = _BLANK_SELECTED.sub('\u3000\u2009', value)
        return (value.replace('\t', '\u2003').replace('\n', '↵').replace('\r', '↵')
                .replace('\ufe0f', '\u200b').replace('\ufe0e', '\u200b'))

    def _value_changed(self, *_):
        if not self._guard.get():
            self._display.set(self._show(self.value.get()))
        self._schedule_paint()

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if hasattr(self, '_native'):
            self._schedule_paint()
        return result

    config = configure

    def _schedule_paint(self, *_):
        if self._paint_job is None:
            self._paint_job = self.after_idle(self._paint_marks)

    def _edge(self, index, width):
        # Entry.bbox returns zero rectangles on this Windows Tk. Its native
        # pixel-to-index map also accounts for scrolling and proportional fonts.
        lo, hi = 0, width
        while lo < hi:
            middle = (lo + hi) // 2
            if self.index('@' + str(middle)) < index:
                lo = middle + 1
            else:
                hi = middle
        return lo

    def _forward_pointer(self, sequence, event):
        self.event_generate(sequence, x=event.x_root-self.winfo_rootx(),
                            y=event.y_root-self.winfo_rooty(), state=event.state,
                            time=event.time)
        self._schedule_paint()
        return 'break'

    def _paint_marks(self):
        self._paint_job = None
        try:
            for mark in self._marks + self._emoji:
                mark.place_forget()
            if not self.winfo_ismapped():
                return
            width, height = self.winfo_width(), self.winfo_height()
            first, last = self.index('@0'), self.index('@' + str(width))
            visible = str(self.tk.call('string', 'range', self.value.get(), first, last))
            selected = (self.index('sel.first'), self.index('sel.last')) if self.selection_present() else None
            if self._font_spec != self.cget('font'):
                self._font_spec = self.cget('font')
                self._font = tkfont.Font(self, font=self._font_spec)
            marker_height = max(4, self._font.metrics('linespace')-2)
            inset = int(self.cget('borderwidth')) + int(self.cget('highlightthickness')) + 1
            colors = self._tab_colors()
            index, used = first, 0
            for char in visible:
                if char == '\t' and not (selected and selected[0] <= index < selected[1]):
                    left = max(inset, self._edge(index, width)) + 1
                    right = min(width-inset, self._edge(index+1, width)) - 1
                    if right > left:
                        if used == len(self._marks):
                            mark = tk.Label(self, borderwidth=0, highlightthickness=0,
                                            takefocus=False, cursor='xterm')
                            for sequence in ('<Button-1>', '<ButtonRelease-1>', '<B1-Motion>'):
                                mark.bind(sequence, lambda e, s=sequence: self._forward_pointer(s, e))
                            self._marks.append(mark)
                        mark = self._marks[used]
                        mark.configure(bg=colors[used % len(colors)])
                        mark.place(x=left, y=(height-marker_height)//2,
                                   width=right-left, height=marker_height)
                        used += 1
                index += self._wide_units if ord(char) > 0xffff else 1
            self._paint_emoji(first, visible, selected, width, height, inset)
        except tk.TclError:
            # A queued redraw may arrive during destruction of its dialog.
            return

    def _paint_emoji(self, first, visible, selected, width, height, inset):
        """Colour emoji over the field as over the memo (emoji_color): Tk
        8.6.9 draws them black and white (2026-10-15 うにさん「検索ウインドウで、
        色が付かず」). Only where Direct2D draws them; the value is untouched."""
        import emoji_color
        spans = emoji_color.emoji_spans(visible)
        if not spans:
            return
        render = emoji_color.renderer()
        if render is None:
            return
        units = lambda text: sum(self._wide_units if ord(c) > 0xffff else 1 for c in text)
        line = max(4, self._font.metrics('linespace'))
        top = max(inset, (height - line) // 2)
        line = min(line, height - 2 * inset)
        for used, (a, b) in enumerate(spans):
            start, end = first + units(visible[:a]), first + units(visible[:b])
            left = max(inset, self._edge(start, width)) + 1
            right = min(width - inset, self._edge(end, width)) - 1
            if right - left < 4:
                continue
            chosen = selected and selected[0] <= start < selected[1]
            bg = str(self.cget('selectbackground') if chosen else self.cget('bg'))
            r, g, b_ = self.winfo_rgb(bg)
            bg = '#%02x%02x%02x' % (r >> 8, g >> 8, b_ >> 8)
            key = (visible[a:b], right - left, line, bg)
            image = self._emoji_images.get(key)
            if image is None:
                if len(self._emoji_images) > 200:
                    self._emoji_images.clear()
                px = max(8, round(min(right - left + 2, line) * 0.78))
                image = self._emoji_images[key] = tk.PhotoImage(
                    master=self, data=render.render(visible[a:b], px, right - left, line, bg))
            while len(self._emoji) <= used:
                label = tk.Label(self, borderwidth=0, highlightthickness=0, padx=0, pady=0,
                                 takefocus=False, cursor='xterm')
                for sequence in ('<Button-1>', '<ButtonRelease-1>', '<B1-Motion>'):
                    label.bind(sequence, lambda e, s=sequence: self._forward_pointer(s, e))
                self._emoji.append(label)
            label = self._emoji[used]
            label.configure(image=image)
            label.place(x=left, y=top, width=right - left, height=line)

    def _destroyed(self, event):
        if event.widget is not self:
            return
        if self._paint_job is not None:
            self.after_cancel(self._paint_job)
            self._paint_job = None
        self.value.trace_remove('write', self._value_trace)
        try:
            self.tk.call('rename', self._w, '')
        except tk.TclError:
            pass
