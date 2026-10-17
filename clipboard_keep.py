# -*- coding: utf-8 -*-
"""Lend the clipboard to one paste, then give back what was there.

2026-10-16 うにさん: quick input (on closing) and the word book (on a click)
put their text on the clipboard; each gets an option, default on, to leave
the clipboard alone. With the option off, CorrectNote's own fields still get
the text directly. Another app's text box can only be reached with Ctrl+V,
which reads the clipboard: so the current contents are saved first, the text
is put there for that one paste, and once the other app has had time to read
it, the saved contents are put back.

Saved and put back: every format whose data is a memory block (HGLOBAL) —
CF_UNICODETEXT, CF_DIB/CF_DIBV5, CF_HDROP, "HTML Format", "Rich Text Format",
PNG, ... — and CF_ENHMETAFILE (copied). Windows makes CF_TEXT, CF_BITMAP and
CF_METAFILEPICT again from those. Not put back: formats that are handles to
other objects (CF_PALETTE, owner-display, private and GDI-object formats).
Nothing is put back if someone else changed the clipboard in the meantime
(the user copied something new: theirs wins).

Neither the lent text nor the contents put back go to the clipboard history
(Win+V) or the cloud clipboard: each time, the registered formats below are
placed with them, as Windows documents for such programs.
"""
import sys
import time

# The other app reads the clipboard when it handles Ctrl+V. Wait this long
# after sending it before putting the old contents back.
RESTORE_DELAY_MS = 1000
CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
# Handles to other objects: their memory is not a copyable block.
_HANDLE_FORMATS = {2, 3, 9, 0x80, 0x82, 0x83, 0x8E}     # BITMAP METAFILEPICT PALETTE OWNERDISPLAY DSP*
# Keep out of the clipboard history and the cloud clipboard (name: data).
PRIVATE_MARKS = (('ExcludeClipboardContentFromMonitorProcessing', b''),
                 ('CanIncludeInClipboardHistory', b'\0\0\0\0'),
                 ('CanUploadToCloudClipboard', b'\0\0\0\0'))


def _mark_private(b):
    for name, data in PRIVATE_MARKS:
        fmt = b.register(name)
        if fmt:
            b.put(fmt, data)


class Saved:
    """One borrowing of the clipboard. restore() puts the old contents back."""

    def __init__(self, backend, items, skipped, sequence):
        self.backend, self.items, self.skipped = backend, items, skipped
        self.sequence = sequence
        self.done = False

    def restore(self):
        """Put the saved contents back. False if the clipboard changed since
        the text was lent, or it could not be opened (then it is left as is)."""
        if self.done:
            return False
        self.done = True
        b = self.backend
        if b.sequence() != self.sequence or not b.open():
            for fmt, data in self.items:
                b.discard(data)
            return False
        try:
            b.empty()
            for fmt, data in self.items:
                b.put(fmt, data)
            _mark_private(b)
        finally:
            b.close()
        return True


def _keepable(fmt):
    if fmt in _HANDLE_FORMATS:
        return False
    if 0x200 <= fmt <= 0x3FF:       # private (CF_PRIVATEFIRST..) and GDI-object formats
        return False
    return True


def lend(text, backend=None):
    """Save the clipboard, then put `text` there. Returns Saved, or None when
    the clipboard could not be used (then nothing was changed)."""
    b = backend or _backend()
    if b is None or not b.open():
        return None
    items, skipped = [], []
    try:
        for fmt in b.formats():
            if not _keepable(fmt):
                skipped.append(fmt)
                continue
            data = b.take(fmt)
            if data is None:
                skipped.append(fmt)
            else:
                items.append((fmt, data))
        private = {b.register(name) for name, data in PRIVATE_MARKS}
        items = [(fmt, data) for fmt, data in items if fmt not in private]
        b.empty()
        if not b.put(CF_UNICODETEXT, text):
            # The text is not there: put the old contents straight back.
            b.empty()
            for fmt, data in items:
                b.put(fmt, data)
            _mark_private(b)
            return None
        _mark_private(b)
    finally:
        b.close()
    return Saved(b, items, skipped, b.sequence())


_BACKEND = None


def _backend():
    global _BACKEND
    if sys.platform != 'win32':
        return None
    if _BACKEND is None:
        _BACKEND = _Win32()
    return _BACKEND


class _Win32:
    """The real Windows clipboard (ctypes). Tests use a stand-in instead."""

    def __init__(self):
        import ctypes as C
        from ctypes import wintypes as W
        self.C = C
        u = C.WinDLL('user32', use_last_error=True)
        k = C.WinDLL('kernel32', use_last_error=True)
        g = C.WinDLL('gdi32', use_last_error=True)
        for lib, name, args, result in (
                (u, 'OpenClipboard', [W.HWND], W.BOOL),
                (u, 'CloseClipboard', [], W.BOOL),
                (u, 'EmptyClipboard', [], W.BOOL),
                (u, 'EnumClipboardFormats', [W.UINT], W.UINT),
                (u, 'GetClipboardData', [W.UINT], W.HANDLE),
                (u, 'SetClipboardData', [W.UINT, W.HANDLE], W.HANDLE),
                (u, 'GetClipboardSequenceNumber', [], W.DWORD),
                (u, 'RegisterClipboardFormatW', [W.LPCWSTR], W.UINT),
                (k, 'GlobalAlloc', [W.UINT, C.c_size_t], W.HGLOBAL),
                (k, 'GlobalFree', [W.HGLOBAL], W.HGLOBAL),
                (k, 'GlobalLock', [W.HGLOBAL], C.c_void_p),
                (k, 'GlobalUnlock', [W.HGLOBAL], W.BOOL),
                (k, 'GlobalSize', [W.HGLOBAL], C.c_size_t),
                (g, 'CopyEnhMetaFileW', [W.HANDLE, W.LPCWSTR], W.HANDLE),
                (g, 'DeleteEnhMetaFile', [W.HANDLE], W.BOOL)):
            fn = getattr(lib, name)
            fn.argtypes = args
            fn.restype = result
        self.u, self.k, self.g = u, k, g

    def open(self):
        # Another program may hold it for a moment.
        for _ in range(10):
            if self.u.OpenClipboard(None):
                return True
            time.sleep(0.01)
        return False

    def close(self):
        self.u.CloseClipboard()

    def empty(self):
        self.u.EmptyClipboard()

    def sequence(self):
        return int(self.u.GetClipboardSequenceNumber())

    def register(self, name):
        return int(self.u.RegisterClipboardFormatW(name))

    def formats(self):
        out, fmt = [], 0
        while True:
            fmt = self.u.EnumClipboardFormats(fmt)
            if not fmt:
                return out
            out.append(int(fmt))

    def take(self, fmt):
        handle = self.u.GetClipboardData(fmt)
        if not handle:
            return None
        if fmt == CF_ENHMETAFILE:
            copy = self.g.CopyEnhMetaFileW(handle, None)
            return ('emf', copy) if copy else None
        size = self.k.GlobalSize(handle)
        pointer = self.k.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return self.C.string_at(pointer, size)
        finally:
            self.k.GlobalUnlock(handle)

    def discard(self, data):
        if isinstance(data, tuple) and data[0] == 'emf':
            self.g.DeleteEnhMetaFile(data[1])

    def put(self, fmt, data):
        if isinstance(data, tuple) and data[0] == 'emf':
            return bool(self.u.SetClipboardData(fmt, data[1]))
        if isinstance(data, str):
            data = (data + '\0').encode('utf-16-le')
        handle = self.k.GlobalAlloc(0x0002, max(1, len(data)))     # GMEM_MOVEABLE
        if not handle:
            return False
        pointer = self.k.GlobalLock(handle)
        if not pointer:
            self.k.GlobalFree(handle)
            return False
        self.C.memmove(pointer, data, len(data))
        self.k.GlobalUnlock(handle)
        if not self.u.SetClipboardData(fmt, handle):
            self.k.GlobalFree(handle)
            return False
        return True
