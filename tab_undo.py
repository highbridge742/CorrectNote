# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Each file tab keeps its own Undo/Redo (2026-11-03 うにさん: カット → 別のタブへ → 戻ると、何度 Undo しても
戻らない). The one Text shows every tab, and its history went with each switch.

Memory only, never written to a file. undo_feedback keeps the steps; here they wait for the tab's return.
Ctrl+Z takes the newest edit over all the tabs, going to its tab and showing the place: an undo that changes another
tab would read as if the text had come back. Ctrl+Y goes the same way back. The steps carry their order
(undo_feedback.next_seq). The steps that are not text (bold, the ruler, a re-choice) are in the same one order.
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
        app.editor._correctnote_observers['replay_gate'] = self.gate
        app.editor._correctnote_observers['step_taken'] = self.step_taken

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

    def _owners(self):
        """Who keeps steps that are not text: bold and the like, the ruler, a re-choice. A new kind joins by giving
        step_top and step_drop beside its undo hook."""
        observers = getattr(self.app.editor, '_correctnote_observers', None) or {}
        found = []
        for hook in observers.get('undo_hooks', ()):
            owner = getattr(hook, '__self__', None)
            if hasattr(owner, 'step_top'):
                found.append(owner)
        return found

    def _tab_of_text(self, text):
        """The tab whose text this is: this one first, as two tabs can hold the same text."""
        from analysis_work import same_step_text
        session = self.app.session
        if same_step_text(text, self.app.editor.get('1.0', 'end-1c')):
            return self.owner
        for tab in session.tabs:
            if tab is not self.owner and same_step_text(text, tab.get('text') or ''):
                return tab
        return None

    def _next_step(self, kind):
        """(the tab of the next step over all the tabs, or None when there is none) in one order: Undo the newest,
        Redo the same way back. A step whose text is nowhere waits while an edit that came after it is still to go;
        when nothing else is before it, its text is gone for good and the step goes."""
        undo = kind == 'undo'
        better = (lambda a, b: a > b) if undo else (lambda a, b: a < b)
        while True:
            best = None         # (number, tab)
            own = self.feedback.next_seq(kind)
            if own is not None:
                best = (own, self.owner)
            for k in self.kept:
                if k[kind] and (best is None or better(k[kind][-1][0], best[0])):
                    best = (k[kind][-1][0], k['tab'])
            lost = None
            for owner in self._owners():
                top = owner.step_top(kind)
                if top is None:
                    continue
                if best is None or better(top[0], best[0]):
                    tab = top[2] if top[2] is not None else self._tab_of_text(top[1])
                    alive = tab is not None and any(tab is t for t in self.app.session.tabs)
                    if alive:
                        best = (top[0], tab)
                    elif lost is None or better(top[0], lost[0]):
                        lost = (top[0], owner)
            if lost is None or (best is not None and better(best[0], lost[0])):
                return best[1] if best is not None else None
            lost[1].step_drop(kind)

    def step_taken(self, hook):
        """A step that is not text came back: when its place is out of view, go there, or it reads as if nothing
        happened (2026-11-04). A place in view leaves the cursor alone."""
        import tkinter as tk
        editor = self.app.editor
        place = getattr(getattr(hook, '__self__', None), 'last_place', None)
        if not place:
            return
        try:
            if editor.bbox(place) is None:
                editor.mark_set('insert', place)
                editor.see('insert')
        except tk.TclError:
            pass

    def gate(self, kind):
        """Ctrl+Z / Ctrl+Y here: is the next step over all the tabs in another tab? Then go there, afterwards: this runs
        inside the Text's own command. うにさん 2026-11-04: カットして別のタブへ移り、そのタブに前からの編集があると、
        そちらが戻って、カットの字は消えたままだった。書式・ルーラーも同じ順番。"""
        if getattr(self.app.editor, '_correctnote_undo_here', False):
            return False
        # A text step with no number (its history was cut short) stays first: its place is not known
        if self.feedback.next_seq(kind) is None and int(self.app.editor.edit('can' + kind)):
            return False
        tab = self._next_step(kind)
        if tab is None or tab is self.owner:
            return False
        try:
            self.app.root.after_idle(lambda: self._go(kind))
        except Exception:
            return False
        return True

    def _go(self, kind):
        import tkinter as tk
        app = self.app
        if getattr(app, '_closing', False):
            return
        # Asked again: two quick presses both land here, and the first has moved already
        tab = self._next_step(kind)
        owners = self._owners()
        for owner in owners:
            owner.last_place = None
        if tab is not None and tab is not self.owner:
            for i, t in enumerate(app.session.tabs):
                if t is tab:
                    app._switch_tab(i)
                    break
        try:
            (app.editor.edit_undo if kind == 'undo' else app.editor.edit_redo)()
        except tk.TclError:
            return
        # The place that came back, not where the tab was left
        app._pending_scroll = 0
        app._pending_scroll_top = None
        for owner in owners:
            if getattr(owner, 'last_place', None):
                try:
                    app.editor.mark_set('insert', owner.last_place)
                except tk.TclError:
                    pass
        app._on_change()
        app.editor.see('insert')
        app.root.after_idle(lambda: app.editor.see('insert'))
