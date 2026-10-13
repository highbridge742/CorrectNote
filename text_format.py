# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Bold, italic, underline and strikethrough as presentation tags.

The text itself, the analysis and the undo history never change. The styles
are Tk tags on the input pane and are kept per tab in the session (rows and
Python character columns of the source text), not in the saved text file.
"""
import tkinter as tk
import tkinter.font as tkfont
from pos_font import POS_CATEGORIES, POS_FONT_TAGS, font_size, normalize_multipliers
from session import TEXT_STYLE_KEYS, clean_text_styles as clean_styles

STYLES = (
    ('bold', 'B', 'ボールド', 'Ctrl+B、Ctrl+2'),
    ('italic', 'I', '斜体', 'Ctrl+I、Ctrl+3'),
    ('underline', 'U', '下線', 'Ctrl+U、Ctrl+4'),
    ('overstrike', 'S', '取り消し線', 'Ctrl+5'),
)
STYLE_KEYS = tuple(key for key, *_ in STYLES)
assert STYLE_KEYS == TEXT_STYLE_KEYS
STYLE_TAGS = {key: 'fmt_' + key for key in STYLE_KEYS}
# Key names for Ctrl+key. Letters arrive upper-case with Shift or Caps Lock.
SHORTCUTS = {
    'b': 'bold', 'B': 'bold', '2': 'bold',
    'i': 'italic', 'I': 'italic', '3': 'italic',
    'u': 'underline', 'U': 'underline', '4': 'underline',
    '5': 'overstrike',
}
_VARIANTS = {(True, False): 'b', (False, True): 'i', (True, True): 'bi'}
_NAVIGATION_KEYS = frozenset(('Left', 'Right', 'Up', 'Down', 'Home', 'End',
                              'Prior', 'Next', 'KP_Left', 'KP_Right', 'KP_Up',
                              'KP_Down', 'KP_Home', 'KP_End', 'KP_Prior',
                              'KP_Next'))


def font_tag(major, variant):
    """Display tag combining a POS size (or the pane size) with bold/italic."""
    base = 'base' if major is None else str(POS_CATEGORIES.index(major))
    return 'fmt_font_' + base + '_' + variant


FONT_TAGS = tuple(font_tag(major, variant)
                  for major in (None,) + POS_CATEGORIES
                  for variant in _VARIANTS.values())
_POS_BY_TAG = {tag: major for major, tag in POS_FONT_TAGS.items()}


def _key(index):
    row, col = str(index).split('.')
    return int(row), int(col)


_TCL_COLUMN_WIDTH = {}


def _position(widget, index):
    """(row, Python column). Tk 8.6 on Windows reports UTF-16 columns, and
    feeding such a numeric index back moves it after an emoji."""
    native = str(index)
    if not native.replace('.', '', 1).isdigit() or native.count('.') != 1:
        native = widget.index(index)
    row, column = _key(native)
    key = id(widget.tk)
    width = _TCL_COLUMN_WIDTH.get(key)
    if width is None:
        width = _TCL_COLUMN_WIDTH[key] = int(widget.tk.call('string', 'length', '\U0001f600'))
    if width == 1 or column == 0:
        return row, column
    line = widget.get(f'{row}.0', f'{row}.end')
    prefix = line.encode('utf-16-le', 'surrogatepass')[:column * 2]
    return row, len(prefix.decode('utf-16-le', 'surrogatepass'))


def _stable(widget, index):
    row, column = _position(widget, index)
    return f'{row}.0+{column}c'


def project(styles, source_lines, target_lines):
    """Map ``capture()`` ranges onto rows whose text was corrected.

    Each row is projected on its own with ``map_column``; a range never
    crosses a line break in the result, and edges inside a replaced word
    keep the whole replacement."""
    from text_positions import map_column
    result = {}
    for key, ranges in clean_styles(styles).items():
        rows = {}
        for row, col, row2, col2 in ranges:
            for current in range(row, row2 + 1):
                if current > len(source_lines) or current > len(target_lines):
                    break
                source, target = source_lines[current - 1], target_lines[current - 1]
                a = col if current == row else 0
                z = min(col2 if current == row2 else len(source), len(source))
                if a >= z:
                    continue
                if source != target:
                    a = map_column(source, target, a, edge='start')
                    z = map_column(source, target, z, edge='end')
                if a < z:
                    rows.setdefault(current, []).append([a, z])
        items = []
        for current in sorted(rows):
            merged = []
            for a, z in sorted(rows[current]):
                if merged and a <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], z)
                else:
                    merged.append([a, z])
            items.extend([current, a, current, z] for a, z in merged)
        if items:
            result[key] = items
    return result


class TextFormat:
    def __init__(self, app, widget, editable=True):
        self.app, self.widget = app, widget
        self.pending = {}
        self._buttons = {}
        self._button_job = None
        self._font_signature = None
        self._font_tags_used = False
        self.listeners = []
        widget.tag_configure(STYLE_TAGS['underline'], underline=1)
        widget.tag_configure(STYLE_TAGS['overstrike'], overstrike=1)
        if not editable:
            # A read-only copy (the correction pane) only shows the styles.
            self.configure()
            return
        widget.mark_set('fmt_typing_anchor', 'insert')
        widget.mark_gravity('fmt_typing_anchor', 'left')
        from analysis_work import observe_text
        observe_text(widget)
        widget._correctnote_observers.setdefault('changed', []).append(self.changed)
        for key, (sequences) in (
                ('bold', ('<Control-b>', '<Control-B>', '<Control-Key-2>')),
                ('italic', ('<Control-i>', '<Control-I>', '<Control-Key-3>')),
                ('underline', ('<Control-u>', '<Control-U>', '<Control-Key-4>')),
                ('overstrike', ('<Control-Key-5>',))):
            for sequence in sequences:
                widget.bind(sequence, lambda event, k=key: self.shortcut(event, k))
        widget.bind('<ButtonPress-1>', self.moved, add=True)
        widget.bind('<KeyPress>', self.key_moved, add=True)
        for sequence in ('<ButtonRelease-1>', '<KeyRelease>', '<<Selection>>'):
            widget.bind(sequence, self.queue_buttons, add=True)
        self.configure()

    # --- fonts -------------------------------------------------------
    def configure(self):
        """Fonts for bold/italic, also inside POS-sized words."""
        w = self.widget
        try:
            settings = getattr(self.app, 'settings', None)
            multipliers = normalize_multipliers(
                settings.get('pos_font_multipliers') if settings is not None else None)
            spec = str(w.cget('font'))
            signature = (spec, tuple(sorted(multipliers.items())))
            if signature == self._font_signature:
                return
            actual = tkfont.Font(root=w, font=spec).actual()
            family = actual.get('family') or 'Yu Mincho'
            size = abs(int(actual.get('size') or 10))
            for major in (None,) + POS_CATEGORIES:
                scaled = size if major is None else font_size(size, multipliers[major])
                for (bold, italic), variant in _VARIANTS.items():
                    style = (('bold',) if bold else ()) + (('italic',) if italic else ())
                    w.tag_configure(font_tag(major, variant), font=(family, scaled) + style)
            # POS sizes are lowest; the POS-specific combinations win over base.
            for tag in FONT_TAGS:
                w.tag_raise(tag)
            for major in POS_CATEGORIES:
                for variant in _VARIANTS.values():
                    w.tag_raise(font_tag(major, variant))
            self._font_signature = signature
        except (tk.TclError, TypeError, ValueError):
            self._font_signature = None

    def refresh_fonts(self):
        self._font_signature = None
        self.configure()
        self.paint('1.0', 'end')

    def _has_font_styles(self):
        w = self.widget
        return bool(w.tag_ranges(STYLE_TAGS['bold']) or w.tag_ranges(STYLE_TAGS['italic']))

    def paint(self, start, end):
        """Recompute bold/italic display fonts for whole rows in a range."""
        w = self.widget
        try:
            first = _key(w.index(start))[0]
            last = _key(w.index(end))[0]
            row_start, row_end = f'{first}.0', f'{last}.end'
            styled = self._has_font_styles()
            if not styled and not self._font_tags_used:
                return
            for tag in FONT_TAGS:
                w.tag_remove(tag, row_start, row_end)
            self._font_tags_used = styled
            if not styled:
                return
            bold, italic = STYLE_TAGS['bold'], STYLE_TAGS['italic']
            points = {_position(w, row_start), _position(w, row_end)}
            for tag in (bold, italic) + tuple(POS_FONT_TAGS.values()):
                index = row_start
                while True:
                    found = w.tag_nextrange(tag, index, row_end)
                    if not found:
                        break
                    found = [_position(w, i) for i in found]
                    points.update(found)
                    index = '%d.0+%dc' % found[1]
                previous = w.tag_prevrange(tag, row_start)
                if previous:
                    point = _position(w, previous[1])
                    if point > (first, 0):
                        points.add(point)
            ordered = sorted(points)
            for a, z in zip(ordered, ordered[1:]):
                if not a < z:
                    continue
                a, z = '%d.0+%dc' % a, '%d.0+%dc' % z
                names = w.tag_names(a)
                variant = _VARIANTS.get((bold in names, italic in names))
                if variant is None:
                    continue
                major = next((_POS_BY_TAG[name] for name in reversed(names)
                              if name in _POS_BY_TAG), None)
                w.tag_add(font_tag(major, variant), a, z)
        except tk.TclError:
            pass

    # --- state -------------------------------------------------------
    def _selection(self):
        try:
            return (_stable(self.widget, 'sel.first'),
                    _stable(self.widget, 'sel.last'))
        except tk.TclError:
            return None

    def _covers(self, tag, start, end):
        w = self.widget
        found = w.tag_prevrange(tag, f'{start}+1c')
        if not found:
            return False
        first, last = (_position(w, index) for index in found)
        return first <= _position(w, start) and last >= _position(w, end)

    def active(self, key):
        tag = STYLE_TAGS[key]
        selection = self._selection()
        if selection is not None:
            return self._covers(tag, *selection)
        if key in self.pending:
            return self.pending[key]
        w = self.widget
        try:
            if w.compare('insert', '==', 'insert linestart'):
                return tag in w.tag_names('insert')
            return tag in w.tag_names('insert-1c')
        except tk.TclError:
            return False

    def toggle(self, key):
        w = self.widget
        tag = STYLE_TAGS[key]
        selection = self._selection()
        if selection is not None:
            start, end = selection
            if self._covers(tag, start, end):
                w.tag_remove(tag, start, end)
            else:
                w.tag_add(tag, start, end)
            self.paint(start, end)
        else:
            self.pending[key] = not self.active(key)
            w.mark_set('fmt_typing_anchor', 'insert')
        self._schedule_save()
        self.refresh_buttons()
        self._notify()
        return 'break'

    def shortcut(self, event, key):
        self.toggle(key)
        return 'break'

    def moved(self, event=None):
        self.pending.clear()
        self.queue_buttons()

    def key_moved(self, event):
        if getattr(event, 'keysym', '') in _NAVIGATION_KEYS:
            self.pending.clear()

    def changed(self, args=None):
        if not self.pending or not args or args[0] not in ('insert', 'replace'):
            return
        w = self.widget
        try:
            if not w.compare('fmt_typing_anchor', '<', 'insert'):
                return
            anchor = _stable(w, 'fmt_typing_anchor')
            for key, on in self.pending.items():
                if on:
                    w.tag_add(STYLE_TAGS[key], anchor, 'insert')
                else:
                    w.tag_remove(STYLE_TAGS[key], anchor, 'insert')
            self.paint(anchor, 'insert')
        except tk.TclError:
            pass
        self._notify()

    def _notify(self):
        for listener in tuple(self.listeners):
            try:
                listener()
            except Exception:
                pass

    def mirror_to(self, target):
        """Show these styles on ``target`` (the correction pane)."""
        source_lines = self.widget.get('1.0', 'end-1c').split('\n')
        target_lines = target.widget.get('1.0', 'end-1c').split('\n')
        styles = project(self.capture(), source_lines, target_lines)
        if styles != target.capture():
            target.restore(styles)
        return styles

    def _schedule_save(self):
        schedule = getattr(self.app, '_schedule_session_save', None)
        if schedule is not None:
            try:
                schedule()
            except Exception:
                pass

    # --- toolbar -----------------------------------------------------
    def attach_button(self, key, button):
        self._buttons[key] = button
        self.refresh_buttons()

    def queue_buttons(self, event=None):
        if self._button_job is None:
            try:
                self._button_job = self.widget.after_idle(self.refresh_buttons)
            except tk.TclError:
                self._button_job = None

    def refresh_buttons(self):
        self._button_job = None
        palette = getattr(self.app, '_format_button_palette', None)
        for key, button in self._buttons.items():
            try:
                on = self.active(key)
                colors = palette(on) if palette is not None else {}
                button.configure(relief='sunken' if on else 'flat', **colors)
            except tk.TclError:
                pass

    # --- session -----------------------------------------------------
    def capture(self, source_lines=None):
        """Ranges as [row, col, row, col] in Python characters of the source."""
        from text_positions import map_column
        w = self.widget
        result = {}
        for key in STYLE_KEYS:
            ranges = w.tag_ranges(STYLE_TAGS[key])
            items = []
            for start, end in zip(ranges[0::2], ranges[1::2]):
                points = []
                for index in (start, end):
                    row, col = _position(w, index)
                    if source_lines is not None and 1 <= row <= len(source_lines):
                        shown = w.get(f'{row}.0', f'{row}.end')
                        if shown != source_lines[row - 1]:
                            col = map_column(shown, source_lines[row - 1], col)
                    points += [row, col]
                if (points[0], points[1]) < (points[2], points[3]):
                    items.append(points)
            if items:
                result[key] = items
        return result

    def restore(self, styles):
        w = self.widget
        self.pending.clear()
        for tag in tuple(STYLE_TAGS.values()) + FONT_TAGS:
            w.tag_remove(tag, '1.0', 'end')
        for key, ranges in clean_styles(styles).items():
            for row, col, row2, col2 in ranges:
                w.tag_add(STYLE_TAGS[key], f'{row}.0+{col}c', f'{row2}.0+{col2}c')
        self.paint('1.0', 'end')
        self.queue_buttons()
        self._notify()


def install(app, widget, editable=True):
    formatter = getattr(widget, '_correctnote_text_format', None)
    if formatter is None:
        formatter = widget._correctnote_text_format = TextFormat(app, widget, editable)
    return formatter
