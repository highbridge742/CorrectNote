# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Cut only once the text is on the clipboard (2026-10-23 うにさん「300行ぐらいを解析中にカットすると、
クリップボードに入らず、消えました」).

Tk's own cut (tk_textCut) clears the clipboard, appends the text and deletes the selection without
knowing whether the clipboard took it: on Windows, Tk's clipboard update does not check that the
clipboard could be opened, so while another program holds it for a moment (a clipboard history, a
program reading the last copy) nothing is put there and the text is deleted all the same
(tools_local/emphasis_20261023/probe_cut.py, with a second process holding the clipboard: 300 rows
gone, nothing on the clipboard, Tk 8.6.9 and 8.6.12 alike). Here the text is put on the clipboard,
read back from it, and only when it is there is the selection deleted; otherwise it is tried again a
few times and, if it still is not there, nothing is deleted.
"""
import sys
import time

TRIES = 4
WAIT_S = 0.08


def _normal(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def clipboard_holds(text, backend=None):
    """Is `text` the plain text on the clipboard now? Reading it makes Tk render its copy."""
    if sys.platform != 'win32':
        return True
    import clipboard_keep
    b = backend or clipboard_keep._backend()
    if b is None or not b.open():
        return False
    try:
        data = b.take(clipboard_keep.CF_UNICODETEXT)
    finally:
        b.close()
    if not data:
        return False
    try:
        got = bytes(data).decode('utf-16-le', 'replace').split('\0', 1)[0]
    except Exception:
        return False
    return _normal(got) == _normal(text)


def put_verified(widget, text, tries=TRIES, wait=WAIT_S, backend=None):
    """Put `text` (with its B/I/U/S, as rich_copy does) on the clipboard and make sure it is there.
    True when it is; False when it never got there (the caller then keeps the text)."""
    for attempt in range(tries):
        try:
            rich = None
            try:
                import rich_copy
                runs = rich_copy.styled_runs(widget, 'sel.first', 'sel.last')
                rich = runs if rich_copy.has_styles(runs) else None
            except Exception:
                rich = None
            if rich is not None and rich_copy.put(text, rich):
                pass
            else:
                widget.clipboard_clear()
                widget.clipboard_append(text)
        except Exception:
            pass
        if clipboard_holds(text, backend):
            return True
        time.sleep(wait * (attempt + 1))
    return False
