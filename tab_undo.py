# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Each file tab keeps its own Undo/Redo (2026-11-03 うにさん: カット → 別のタブへ → 戻ると、何度 Undo しても
戻らない). The one Text shows every tab, and its history went with each switch.

Memory only, never written to a file. undo_feedback keeps the steps; here they wait for the tab's return.
A Ctrl+Z in a tab with nothing of its own goes to the tab with the last edit and undoes there: an undo in a
tab that changes nothing would read as if the text had come back. The steps carry their order (undo_feedback.next_seq),
so one history over all the tabs would need only the choice of the tab here.
"""

TAB_CHARS = 1000000     # one tab's steps, oldest dropped first (the newest is kept whatever its size)
ALL_CHARS = 4000000     # all the tabs' together


def _chars(entry):
    return sum(len(a) + len(b) for _start, a, b in entry[2])


def _size(snapshot):
    return sum(map(_chars, snapshot['undo'])) + sum(map(_chars, snapshot['redo']))


def _trim(entries, limit):
    total = sum(map(_chars, entries))
    while total > limit and len(entries) > 1:
        total -= _chars(entries.pop(0))


class TabUndo:
    def __init__(self, app, feedback):
        self.app = app
        self.feedback = feedback
        self.kept = []      # dict(tab=the tab, text=hash of its text, undo=[...], redo=[...])
        self.owner = None   # the tab the memo shows
        feedback.on_empty = self.undo_elsewhere

    def _text(self):
        return self.app.editor.get('1.0', 'end-1c').rstrip('\n')

    def leave(self):
        """Before the memo takes another tab's text."""
        tab, self.owner = self.owner, None
        tabs = self.app.session.tabs
        self.kept = [k for k in self.kept if any(k['tab'] is t for t in tabs)]
        if tab is None or not any(tab is t for t in tabs):
            return
        snapshot = self.feedback.take()
        if not snapshot['undo'] and not snapshot['redo']:
            return
        _trim(snapshot['undo'], TAB_CHARS)
        self.kept.append(dict(snapshot, tab=tab, text=hash(self._text())))
        self._trim_all()

    def _trim_all(self):
        total = sum(map(_size, self.kept))
        while total > ALL_CHARS:
            lists = [k['undo'] for k in self.kept if len(k['undo']) > 1]
            if not lists:
                break
            oldest = min(lists, key=lambda entries: entries[0][0])
            total -= _chars(oldest.pop(0))

    def enter(self, tab):
        """After the memo has the tab's text and its history was reset."""
        self.owner = tab
        for i, k in enumerate(self.kept):
            if k['tab'] is tab:
                del self.kept[i]
                # Its text changed while away (a file read again): the steps no longer fit
                if k['text'] == hash(self._text()):
                    self.feedback.give(k)
                return

    def last_edited(self):
        """The index of the kept tab whose next undo is the newest edit, or None."""
        best = None
        for k in self.kept:
            if k['undo'] and (best is None or k['undo'][-1][0] > best['undo'][-1][0]):
                best = k
        if best is None:
            return None
        for i, tab in enumerate(self.app.session.tabs):
            if tab is best['tab']:
                return i
        return None

    def undo_elsewhere(self):
        """A Ctrl+Z here with nothing to undo. Afterwards: this runs inside the Text's own command."""
        if self.last_edited() is None:
            return
        try:
            self.app.root.after_idle(self._go)
        except Exception:
            pass

    def _go(self):
        import tkinter as tk
        app = self.app
        index = self.last_edited()
        if index is None or getattr(app, '_closing', False):
            return
        app._switch_tab(index)
        try:
            app.editor.edit_undo()
        except tk.TclError:
            return
        # The place that came back, not where the tab was left
        app._pending_scroll = 0
        app._pending_scroll_top = None
        app._on_change()
        app.editor.see('insert')
        app.root.after_idle(lambda: app.editor.see('insert'))
