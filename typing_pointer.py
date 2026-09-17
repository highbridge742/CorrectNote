# -*- coding: utf-8 -*-
"""Hide the app's mouse pointer on typing, restore it on pointer/focus activity."""
import tkinter as tk
import weakref


class TypingPointer:
    def __init__(self, root, panes, is_typing, can_hide=lambda: True):
        self.root = root
        self.panes = panes
        self.is_typing = is_typing
        self.can_hide = can_hide
        self.saved = {}
        self.attached = weakref.WeakSet()
        self.compositions = weakref.WeakKeyDictionary()
        self.tag = 'CorrectNoteTypingPointer' + str(id(self))
        self._own_binding(root.bind_class(self.tag, '<KeyPress>', self._key))
        for sequence in ('<Motion>', '<ButtonPress>', '<MouseWheel>', '<FocusOut>', '<Leave>'):
            self._own_binding(root.bind_class(self.tag, sequence, self.restore))
        # Other controls and auxiliary windows also end the hidden state.
        for sequence in ('<Motion>', '<ButtonPress>', '<MouseWheel>', '<FocusOut>'):
            self._own_binding(root.bind_all(sequence, self.restore, add=True))
        root.bind('<Destroy>', self._destroy, add=True)

    def _own_binding(self, command):
        # Tkinter 3.9 deliberately leaves class/all commands unowned.
        # This controller belongs to one root, so release them with it.
        commands = self.root._tclCommands
        if commands is None:
            commands = self.root._tclCommands = []
        if command not in commands:
            commands.append(command)

    def attach(self, widget):
        self.attached.add(widget)
        tags = widget.bindtags()
        if self.tag not in tags:
            widget.bindtags((self.tag,) + tags)

    def _key(self, event):
        if self.is_typing(event):
            self.hide(event.widget)

    def hide(self, typing_widget=None):
        if self.saved or not self.can_hide():
            return
        widgets = list(self.panes()) + [typing_widget]
        try:
            pointer = self.root.winfo_containing(*self.root.winfo_pointerxy())
            if pointer is not None:
                widgets.append(pointer)
        except tk.TclError:
            pass
        for widget in widgets:
            if widget is None or widget in self.saved:
                continue
            try:
                old = widget.cget('cursor')
                widget.configure(cursor='none')
                self.saved[widget] = old
            except tk.TclError:
                pass

    def poll_composition(self):
        """Use the existing IME timer; unchanged composition never re-hides."""
        try:
            widget = self.root.focus_get()
            if widget not in self.attached or str(widget.cget('state')) != 'normal':
                return
            import ime_watch
            comp = ((ime_watch.read_composition(widget.winfo_id()) or {}).get('comp') or ''
                    if ime_watch.composition_active(widget.winfo_id()) else '')
            previous = self.compositions.get(widget, '')
            self.compositions[widget] = comp
            if comp and comp != previous:
                self.hide(widget)
        except (tk.TclError, AttributeError):
            pass

    def defer_cursor(self, widget, shape):
        """Keep a requested hover/mode shape for restoration, while hidden."""
        if widget not in self.saved:
            return False
        self.saved[widget] = shape
        return True

    def restore(self, event=None):
        if self.saved and event is not None:
            self.poll_composition()
        saved, self.saved = self.saved, {}
        for widget, shape in saved.items():
            try:
                widget.configure(cursor=shape)
            except tk.TclError:
                pass

    def _destroy(self, event):
        if event.widget is self.root:
            self.restore()
