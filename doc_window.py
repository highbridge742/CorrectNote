# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""A tab shown in a second window (2026-10-23 うにさん「ファイルタブの右クリックメニューに『別のウィンドウで
表示する』。新しい窓（同じプロセスの Toplevel）で同じ文書を表示し、元の窓のタブは残す。同じ文書を2つの窓で
開いている間は、片方の編集を即もう片方に反映」).

While the main window shows the same tab, the second window's text box is a Tk peer of the memo: one text,
one undo history, the same tags (the colours per part of speech, the purple marks, B/I/U/S), only the cursor
and the selection its own. Every change typed there is handed to the memo's own command (its positions made
absolute first), so the memo's watchers see it as their own edit: the analysis, the unsaved mark, the saving.

When the main window goes to another tab, the memo widget shows that other tab; the second window then keeps
a plain copy of its document (the text and the B/I/U/S, without the analysis colours) and writes each change
back into the tab's saved text. When the main window comes back to the tab, the memo loads that text and the
second window is a peer again.
"""
import tkinter as tk


class _Peer(tk.Text):
    """A Tk text peer of `original` (tkinter has no wrapper for `peer create`)."""

    def __init__(self, master, original, **kw):
        self._setup(master, {})
        original.tk.call(original._w, 'peer', 'create', self._w, *self._options(kw))


def route_edits(peer, editor):
    """Send the peer's text changes and undo/redo through the memo's command.

    A Tcl procedure, not a Python command (as backup_view.make_read_only, 2026-10-24): the theme switch asks
    every widget for options a Text does not have, and through a Python command that error is kept by
    tkinter and raised again from mainloop(), which ends the app. The positions are made absolute with the
    peer's own `index` (its own insert mark and selection) before the memo's command receives them."""
    real = peer._w + '_doc_window'
    peer.tk.call('rename', peer._w, real)
    peer.tk.call('proc', peer._w, 'args',
                 'switch -- [lindex $args 0] {\n'
                 '    insert {lset args 1 [%(real)s index [lindex $args 1]]; tailcall %(memo)s {*}$args}\n'
                 '    replace {\n'
                 '        lset args 1 [%(real)s index [lindex $args 1]]\n'
                 '        lset args 2 [%(real)s index [lindex $args 2]]\n'
                 '        tailcall %(memo)s {*}$args\n'
                 '    }\n'
                 '    delete {\n'
                 '        for {set i 1} {$i < [llength $args]} {incr i} {lset args $i [%(real)s index [lindex $args $i]]}\n'
                 '        tailcall %(memo)s {*}$args\n'
                 '    }\n'
                 '    edit {if {[lindex $args 1] in {undo redo}} {tailcall %(memo)s edit [lindex $args 1]}}\n'
                 '}\n'
                 'tailcall %(real)s {*}$args' % dict(real=real, memo=editor._w))

    def destroyed(event):
        if event.widget is peer:
            try:
                peer.tk.call('rename', peer._w, '')
            except tk.TclError:
                pass
    peer.bind('<Destroy>', destroyed, add=True)
    return real


class DocumentWindow:
    def __init__(self, app, tab):
        self.app, self.tab = app, tab
        self.text = None
        self.mode = None
        win = self.window = tk.Toplevel(app.root)
        win.protocol('WM_DELETE_WINDOW', self.close)
        try:
            app._set_window_icons_win32(win)
        except Exception:
            pass
        self.body = tk.Frame(win)
        self.body.pack(fill='both', expand=True)
        self.bar = tk.Scrollbar(self.body)
        self.bar.pack(side='right', fill='y')
        win.bind('<Control-s>', self._save)
        win.bind('<Control-S>', self._save)
        # Ctrl+W closes this window, not the main window's tab (2026-10-24 うにさん。the main window's is bind_all)
        win.bind('<Control-w>', self._close_key)
        win.bind('<Control-W>', self._close_key)
        self.show()
        try:
            x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
            win.geometry('%dx%d+%d+%d' % (max(480, app.root.winfo_width() // 2), max(360, app.root.winfo_height() - 80),
                                          x + 40, y + 40))
        except tk.TclError:
            pass
        self.retitle()

    # --- which text box ------------------------------------------------
    def _options(self):
        editor = self.app.editor
        options = {}
        for key in ('font', 'bg', 'fg', 'insertbackground', 'selectbackground', 'selectforeground',
                    'wrap', 'padx', 'pady', 'spacing1', 'spacing2', 'spacing3', 'tabs', 'relief'):
            try:
                options[key] = editor.cget(key)
            except tk.TclError:
                pass
        return options

    def _place(self, text):
        if self.text is not None:
            try:
                self.text.destroy()
            except tk.TclError:
                pass
        self.text = text
        text.configure(yscrollcommand=self._scrolled)
        self.bar.configure(command=text.yview)
        text.pack(side='left', fill='both', expand=True)
        try:
            self.app._install_safe_cut(text)
        except Exception:
            pass
        # Esc while not converting: the copy frame and the larger letters go, as in the main window
        # (2026-10-24 の既定)
        text.bind('<Escape>', self._escape, add=True)
        # The whitespace marks, in the peer and in the copy (app._whitespace_targets lists this text)
        text.bind('<Configure>', lambda e: self._repaint(), add=True)
        try:
            self.app._configure_whitespace_tags()
        except Exception:
            pass
        self._repaint()

    def _scrolled(self, first, last):
        self.bar.set(first, last)
        self._repaint()

    def _repaint(self):
        try:
            self.app._schedule_whitespace_paint(delay=1)
        except Exception:
            pass

    def _escape(self, event=None):
        try:
            self.app._on_copy_frame_escape(event.widget._w if event is not None else None)
        except Exception:
            pass

    def restyle(self):
        """The theme changed: take the memo's colours again."""
        if self.text is None:
            return
        options = {k: v for k, v in self._options().items()
                   if k in ('bg', 'fg', 'insertbackground', 'selectbackground', 'selectforeground')}
        try:
            self.text.configure(**options)
        except tk.TclError:
            pass

    def shown_in_main(self):
        return self.app.session.current() is self.tab

    def show(self):
        """A peer while the main window shows this tab, else a copy."""
        if self.shown_in_main():
            self.attach()
        else:
            self.detach()

    def attach(self):
        """Share the memo (a peer): one text, one undo, the same colours."""
        if self.mode == 'peer':
            return
        top = self._top_line()
        peer = _Peer(self.body, self.app.editor, undo=True, **self._options())
        route_edits(peer, self.app.editor)
        self._place(peer)
        self.mode = 'peer'
        peer.bind('<KeyRelease>', lambda e: self.app._on_change(), add=True)
        peer.bind('<FocusIn>', lambda e: self.app._queue_doc_window_priority(), add=True)
        peer.bind('<MouseWheel>', lambda e: self.app.root.after_idle(self.app._queue_doc_window_priority), add=True)
        self._go_to_line(top)

    def detach(self):
        """The main window shows another tab: keep a copy of this one and write changes back to it."""
        top = self._top_line()
        text = self.text.get('1.0', 'end-1c') if self.text is not None else (self.tab.get('text') or '')
        styles = None
        if self.mode == 'peer':
            formatter = getattr(self.app.editor, '_correctnote_text_format', None)
            try:
                styles = formatter.capture(text.split('\n')) if formatter is not None else None
            except Exception:
                styles = None
        box = tk.Text(self.body, undo=True, **self._options())
        box.insert('1.0', text)
        if styles is None:
            styles = self.tab.get('text_styles') or {}
        try:
            from tkinter import font as tkfont
            from text_format import STYLE_TAGS
            actual = tkfont.Font(root=box, font=box.cget('font')).actual()
            looks = {'bold': dict(font=(actual['family'], actual['size'], 'bold')),
                     'italic': dict(font=(actual['family'], actual['size'], 'italic')),
                     'underline': dict(underline=1), 'overstrike': dict(overstrike=1)}
            for key, spans in (styles or {}).items():
                tag = STYLE_TAGS.get(key)
                if tag is None:
                    continue
                box.tag_configure(tag, **looks.get(key, {}))
                for row, col, row2, col2 in spans:
                    box.tag_add(tag, '%d.0+%dc' % (row, col), '%d.0+%dc' % (row2, col2))
        except Exception:
            pass
        box.edit_reset()
        self._place(box)
        self.mode = 'copy'
        box.bind('<<Modified>>', self._copy_changed, add=True)
        box.edit_modified(False)
        self._go_to_line(top)

    def _copy_changed(self, event=None):
        if self.mode != 'copy' or self.text is None:
            return
        try:
            if not self.text.edit_modified():
                return
            self.text.edit_modified(False)
            text = self.text.get('1.0', 'end-1c')
        except tk.TclError:
            return
        if text != self.tab.get('text'):
            self.tab['text'] = text
            self.tab['saved'] = False
            # B/I/U/S follow the text they are on ([row, col, row, col], as text_format keeps them)
            try:
                # Tk 8.6 on Windows reports UTF-16 columns, and feeding such an index back moves it after an
                # emoji: text_format._position turns Tk's own position into Python characters (2026-10-24)
                from text_format import STYLE_TAGS, _position
                styles = {}
                for key, tag in STYLE_TAGS.items():
                    ranges = self.text.tag_ranges(tag)
                    spans = []
                    for a, z in zip(ranges[0::2], ranges[1::2]):
                        r1, c1 = _position(self.text, a)
                        r2, c2 = _position(self.text, z)
                        spans.append([r1, c1, r2, c2])
                    if spans:
                        styles[key] = spans
                if styles:
                    self.tab['text_styles'] = styles
                else:
                    self.tab.pop('text_styles', None)
            except Exception:
                pass
            self.app._doc_window_edited(self)

    def _top_line(self):
        try:
            return int(self.text.index('@0,0').split('.')[0]) if self.text is not None else 1
        except tk.TclError:
            return 1

    def _go_to_line(self, line):
        try:
            self.text.yview('%d.0' % max(1, line))
        except tk.TclError:
            pass

    def visible_rows(self):
        """(first, last) rows (0-based) shown in this window, or None."""
        if self.mode != 'peer' or self.text is None:
            return None
        try:
            top = int(self.text.index('@0,0').split('.')[0]) - 1
            bottom = int(self.text.index('@0,%d' % max(1, self.text.winfo_height() - 1)).split('.')[0]) - 1
            return top, bottom
        except tk.TclError:
            return None

    def has_focus(self):
        try:
            return self.text is not None and self.app.root.focus_get() is self.text
        except Exception:
            return False

    def retitle(self):
        from session import tab_title
        try:
            mark = '' if self.tab.get('saved', True) else '*'
            self.window.title('%s%s — 別のウィンドウ' % (mark, tab_title(self.tab)))
        except tk.TclError:
            pass

    def _save(self, event=None):
        """Ctrl+S: this tab is saved (the main window goes to it first when it shows another)."""
        app = self.app
        if not self.shown_in_main():
            index = next((i for i, t in enumerate(app.session.tabs) if t is self.tab), None)
            if index is None:
                return 'break'
            app._switch_tab(index)
        app.save_file()
        return 'break'

    def _close_key(self, event=None):
        self.close()
        return 'break'

    def close(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        windows = getattr(self.app, '_doc_windows', None)
        if windows is not None and self in windows:
            windows.remove(self)
