# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Copy bold, italic, underline and strikethrough along with the text (Windows).

2026-10-19 うにさん「ボールド、I,U,Sの書式付き文字をコピーして…ペーストしても、向こうのBIUSに
対応されてペーストされない…書式もコピーできますか」. A copy of a selection that has any of
these styles puts three forms on the clipboard in one operation: the plain text (exactly what
was copied before), "HTML Format" (for Excel, browsers, Outlook) and "Rich Text Format" (for
Word, and for Notepad: the RichEdit inside it reads only the RTF, not the HTML — tried with its
riched20.dll, 2026-10-20). Only B/I/U/S travel: not the font, its size, the part-of-speech
colours or any mark.
A selection without styles is copied as before (plain text only).

In the HTML, lines become <br> (Excel puts them in rows, as it does with plain text) and, when
the text has tabs, a table (Excel puts tab-separated parts in columns, as with plain text)."""
import os
import sys

from text_format import STYLE_TAGS


def styled_runs(widget, start, end):
    """[(text, frozenset(style names))] for the text from `start` to `end` of a tk.Text.
    Only the four style tags are looked at (not the colours and marks on every word), so a
    copy of the whole text without styles costs nothing."""
    start, end = widget.index(start), widget.index(end)
    edges = {start, end}
    for tag in STYLE_TAGS.values():
        for index in widget.tag_ranges(tag):
            index = str(index)
            if widget.compare(start, '<', index) and widget.compare(index, '<', end):
                edges.add(index)
    edges = sorted(edges, key=lambda index: tuple(int(n) for n in index.split('.')))
    runs = []
    for a, z in zip(edges, edges[1:]):
        text = widget.get(a, z)
        if not text:
            continue
        names = widget.tag_names(a)
        styles = frozenset(style for style, tag in STYLE_TAGS.items() if tag in names)
        if runs and runs[-1][1] == styles:
            runs[-1] = (runs[-1][0] + text, styles)
        else:
            runs.append((text, styles))
    return runs


def has_styles(runs):
    return any(styles for _text, styles in runs)


def _html_escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


_HTML_TAGS = (('bold', 'b'), ('italic', 'i'), ('underline', 'u'), ('overstrike', 's'))


def _html_run(text, styles):
    out = _html_escape(text)
    for style, tag in _HTML_TAGS:
        if style in styles:
            out = '<%s>%s</%s>' % (tag, out, tag)
    return out


def html_fragment(runs):
    """The copied text as an HTML fragment: lines in <br> (or table rows when there are tabs)."""
    # Split the styled runs into lines and, within lines, tab-separated cells
    lines = [[[]]]
    for text, styles in runs:
        parts = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        for li, part in enumerate(parts):
            if li:
                lines.append([[]])
            cells = part.split('\t')
            for ci, cell in enumerate(cells):
                if ci:
                    lines[-1].append([])
                if cell:
                    lines[-1][-1].append(_html_run(cell, styles))
    tabbed = any(len(line) > 1 for line in lines)
    if tabbed:
        rows = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % ''.join(cell) for cell in line)
                       for line in lines)
        return '<table>%s</table>' % rows
    return '<br>'.join(''.join(line[0]) for line in lines)


def cf_html(fragment):
    """UTF-8 bytes of the Windows "HTML Format" clipboard data for `fragment`."""
    head = ('Version:0.9\r\nStartHTML:%010d\r\nEndHTML:%010d\r\n'
            'StartFragment:%010d\r\nEndFragment:%010d\r\n')
    prefix = '<html><head><meta charset="utf-8"></head><body><!--StartFragment-->'
    suffix = '<!--EndFragment--></body></html>'
    empty = (head % (0, 0, 0, 0)).encode('utf-8')
    start_html = len(empty)
    start_fragment = start_html + len(prefix.encode('utf-8'))
    end_fragment = start_fragment + len(fragment.encode('utf-8'))
    end_html = end_fragment + len(suffix.encode('utf-8'))
    return ((head % (start_html, end_html, start_fragment, end_fragment))
            + prefix + fragment + suffix).encode('utf-8')


def _rtf_text(text):
    out = []
    for ch in text:
        code = ord(ch)
        if ch in '\\{}':
            out.append('\\' + ch)
        elif ch == '\n':
            out.append('\\par\n')
        elif ch == '\t':
            out.append('\\tab ')
        elif ch == '\r':
            continue
        elif code < 0x80:
            out.append(ch)
        else:
            # Each UTF-16 unit (an emoji is two) as a signed \uN with "?" as the fallback
            data = ch.encode('utf-16-le')
            for i in range(0, len(data), 2):
                unit = data[i] | data[i + 1] << 8
                out.append('\\u%d?' % (unit - 0x10000 if unit >= 0x8000 else unit))
    return ''.join(out)


_RTF_ON = (('bold', '\\b'), ('italic', '\\i'), ('underline', '\\ul'), ('overstrike', '\\strike'))
_RTF_OFF = {'bold': '\\b0', 'italic': '\\i0', 'underline': '\\ulnone', 'overstrike': '\\strike0'}


def rtf(runs):
    """ASCII "Rich Text Format" of the copied text with B/I/U/S only."""
    body = []
    for text, styles in runs:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        on = ''.join(code for style, code in _RTF_ON if style in styles)
        off = ''.join(_RTF_OFF[style] for style, _code in _RTF_ON if style in styles)
        body.append('{%s %s%s}' % (on, _rtf_text(text), off) if on else '{%s}' % _rtf_text(text))
    # No font table: the text takes the font of where it is pasted
    return '{\\rtf1\\ansi\\uc1 ' + ''.join(body) + '}'


# CorrectNote's own form: the text and where its styles are, so that pasting back into CorrectNote
# gives the styles again (2026-10-20 うにさん「太字・斜体・下線・取り消し線を、アプリ内でコピーかカット
# してペーストした場合は、書式も再現する」). Used only when its text is exactly what is pasted.
STYLES_FORMAT = 'CorrectNote.Styles'


def styles_payload(text, runs):
    """UTF-8 JSON: the text with LF line ends and [start, end, styles] in Python characters."""
    import json
    spans, at = [], 0
    for part, styles in runs:
        part = part.replace('\r\n', '\n').replace('\r', '\n')
        if styles and part:
            spans.append([at, at + len(part), sorted(styles)])
        at += len(part)
    plain = text.replace('\r\n', '\n').replace('\r', '\n')
    return json.dumps({'v': 1, 'text': plain, 'runs': spans}, ensure_ascii=False).encode('utf-8') + b'\0'


def parse_styles(data):
    """The payload put by styles_payload, or None."""
    import json
    try:
        value = json.loads(bytes(data).split(b'\0', 1)[0].decode('utf-8'))
    except Exception:
        return None
    if not isinstance(value, dict) or value.get('v') != 1 or not isinstance(value.get('text'), str):
        return None
    spans = []
    for item in value.get('runs') or ():
        try:
            a, z, styles = int(item[0]), int(item[1]), [str(x) for x in item[2]]
        except Exception:
            return None
        if 0 <= a < z <= len(value['text']):
            spans.append((a, z, [x for x in styles if x in STYLE_TAGS]))
    return {'text': value['text'], 'runs': spans}


def read_styles():
    """CorrectNote's own form on the Windows clipboard, or None (nothing is changed)."""
    if sys.platform != 'win32':
        return None
    try:
        import clipboard_keep
        b = clipboard_keep._backend()
        if b is None:
            return None
        fmt = b.register(STYLES_FORMAT)
        if not fmt or not b.open():
            return None
        try:
            data = b.take(fmt) if fmt in b.formats() else None
        finally:
            b.close()
        return parse_styles(data) if data else None
    except Exception:
        return None


def plain_text(text):
    return text.replace('\r\n', '\n').replace('\n', '\r\n')


def put(text, runs):
    """Put the plain text, HTML and RTF on the Windows clipboard in one operation.
    False (nothing changed) when the clipboard could not be opened or a form not set."""
    if sys.platform != 'win32':
        return False
    try:
        import clipboard_keep
        b = clipboard_keep._backend()
        if b is None:
            return False
        # Right after Tk's own copy, programs that watch the clipboard (its history, for one) open
        # it to read the change; give them up to about half a second (each open waits 0.1 s)
        for _ in range(5):
            if b.open():
                break
        else:
            return False
        try:
            b.empty()
            # Lines end in CR LF, as Tk's own copy puts them
            ok = b.put(clipboard_keep.CF_UNICODETEXT, plain_text(text))
            html_format = b.register('HTML Format')
            rtf_format = b.register('Rich Text Format')
            if html_format:
                b.put(html_format, cf_html(html_fragment(runs)) + b'\0')
            if rtf_format:
                b.put(rtf_format, rtf(runs).encode('ascii') + b'\0')
            styles_format = b.register(STYLES_FORMAT)
            if styles_format:
                b.put(styles_format, styles_payload(text, runs))
            return bool(ok)
        finally:
            b.close()
    except Exception:
        return False


def copy(widget, start='sel.first', end='sel.last'):
    """Copy `start`..`end` of `widget` with its styles. Returns the copied text when the styles
    were put on the clipboard, or None when there are none (the caller copies as before)."""
    import tkinter as tk
    try:
        text = widget.get(start, end)
        if not text:
            return None
        runs = styled_runs(widget, start, end)
    except tk.TclError:
        return None
    if not has_styles(runs):
        return None
    return text if put(text, runs) else None


# Tk's own <<Copy>> / <<Cut>> (Ctrl+C, Ctrl+X, Ctrl+Insert, Shift+Delete, the menus) still run,
# so whatever the widget and the "all" bindings do with those keys is unchanged. The styles are
# read before it (a cut deletes the selection) and put on the clipboard after it.
BEFORE_TAG, AFTER_TAG = 'CorrectNoteRichCopyBefore', 'CorrectNoteRichCopyAfter'


def _before(event):
    widget = event.widget
    widget._rich_copy_pending = None
    try:
        if widget.tag_ranges('sel'):
            runs = styled_runs(widget, 'sel.first', 'sel.last')
            if has_styles(runs):
                widget._rich_copy_pending = (widget.get('sel.first', 'sel.last'), runs)
    except Exception:
        pass


def _after(event):
    pending = getattr(event.widget, '_rich_copy_pending', None)
    event.widget._rich_copy_pending = None
    if not pending:
        return
    text, runs = pending
    try:
        # Only over Tk's own copy of the same text, never over something else
        if event.widget.clipboard_get() != text or not _owned_here():
            return
    except Exception:
        return
    put(text, runs)


def _owned_here():
    """True when a window of this process holds the Windows clipboard (Tk's copy took it)."""
    if sys.platform != 'win32':
        return False
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL('user32')
    u.GetClipboardOwner.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    owner = u.GetClipboardOwner()
    if not owner:
        return False
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(owner, ctypes.byref(pid))
    return pid.value == os.getpid()


PASTE_MARK = 'correctnote_rich_paste'


def _before_paste(event):
    widget = event.widget
    widget._rich_paste_pending = None
    try:
        if str(widget.cget('state')) == 'disabled':
            return
        payload = read_styles()
        if not payload:
            return
        # Only when it is exactly what Tk is about to paste (the clipboard may hold other text now)
        if widget.clipboard_get().replace('\r\n', '\n') != payload['text']:
            return
        widget.mark_set(PASTE_MARK, 'insert')
        widget.mark_gravity(PASTE_MARK, 'left')
        widget._rich_paste_pending = payload
    except Exception:
        widget._rich_paste_pending = None


def _after_paste(event):
    widget = event.widget
    payload = getattr(widget, '_rich_paste_pending', None)
    widget._rich_paste_pending = None
    if not payload:
        return
    # Positions stay relative to the mark, counted in characters ("+Nc" counts an emoji as one):
    # after an emoji Tk 8.6 reports numeric columns in UTF-16 units, and such a number read back
    # points one character further (see text_format._position)
    start = PASTE_MARK
    try:
        text = payload['text']
        if widget.get(start, 'insert') != text:
            return
        # The pasted text takes exactly its own styles, not those around where it went
        for tag in STYLE_TAGS.values():
            widget.tag_remove(tag, start, 'insert')
        for a, z, styles in payload['runs']:
            first = '%s+%dc' % (start, a)
            last = '%s+%dc' % (start, z)
            for style in styles:
                widget.tag_add(STYLE_TAGS[style], first, last)
        formatter = getattr(widget, '_correctnote_text_format', None)
        if formatter is not None:
            formatter.paint(start, 'insert')
            formatter._notify()                 # the correction pane shows them too
            formatter._schedule_save()
    except Exception:
        pass
    finally:
        try:
            widget.mark_unset(PASTE_MARK)
        except Exception:
            pass


def install(widget):
    """Copy the styles with Tk's own copy and cut in this tk.Text, and give them back to text
    pasted from CorrectNote's own copy."""
    tags = [t for t in widget.bindtags() if t not in (BEFORE_TAG, AFTER_TAG)]
    if 'Text' not in tags:
        return False
    at = tags.index('Text')
    widget.bindtags(tuple(tags[:at] + [BEFORE_TAG, 'Text', AFTER_TAG] + tags[at + 1:]))
    for sequence in ('<<Copy>>', '<<Cut>>'):
        widget.bind_class(BEFORE_TAG, sequence, _before)
        widget.bind_class(AFTER_TAG, sequence, _after)
    widget.bind_class(BEFORE_TAG, '<<Paste>>', _before_paste)
    widget.bind_class(AFTER_TAG, '<<Paste>>', _after_paste)
    return True
