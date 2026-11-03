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
import sys
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


def _app_module(app):
    """The module the running app's colours live in. `import app` under `py app.py` (where it is __main__) loads a
    second copy, with the first theme's colours: the line numbers came out light in the dark theme (2026-11-03)."""
    module = sys.modules.get(type(app).__module__)
    if module is None or not hasattr(module, 'LineNumberGutter'):
        import app as module
    return module


class DocumentWindow:
    def __init__(self, app, tab):
        self.app, self.tab = app, tab
        self.text = None
        self.mode = None
        win = self.window = tk.Toplevel(app.root)
        # Shown when it is built, at its size: the work below can draw it at the size of nothing yet (2026-11-03
        # うにさん「とても小さく表示され」)
        win.withdraw()
        self._place_window()
        win.protocol('WM_DELETE_WINDOW', self.close)
        try:
            app._set_window_icons_win32(win)
        except Exception:
            pass
        self.gutter = None
        self._build_toolbar()
        self.body = tk.Frame(win)
        self.body.pack(fill='both', expand=True)
        self.bar = tk.Scrollbar(self.body)
        self.bar.pack(side='right', fill='y')
        win.bind('<Control-s>', self._save)
        win.bind('<Control-S>', self._save)
        # Ctrl+W closes this window, not the main window's tab (2026-10-24 うにさん。the main window's is bind_all)
        win.bind('<Control-w>', self._close_key)
        win.bind('<Control-W>', self._close_key)
        try:
            self.show()
        finally:
            win.deiconify()
        self.retitle()

    def _place_window(self):
        """The last second window's size and place in this run, or by the main window; inside its monitor's work area."""
        app = self.app
        root = app.root
        try:
            x, y = root.winfo_rootx() + 40, root.winfo_rooty() + 40
            w, h = max(480, root.winfo_width() // 2), max(360, root.winfo_height() - 80)
            last = getattr(app, '_doc_window_last', None)
            if last:
                w, h, x, y = last
            module = _app_module(app)
            area = module.monitor_work_area(x + w // 2, y + h // 2)
            frame_w, frame_h = module.window_frame_size(root)
            x, y = module.fit_in_area(x, y, w + frame_w, h + frame_h, area)
            self.window.geometry('%dx%d+%d+%d' % (w, h, x, y))
        except (tk.TclError, AttributeError, TypeError, ValueError):
            try:
                self.window.geometry('%dx%d+%d+%d' % (max(480, root.winfo_width() // 2), max(360, root.winfo_height() - 80),
                                                      root.winfo_rootx() + 40, root.winfo_rooty() + 40))
            except tk.TclError:
                pass

    def _remember_place(self):
        try:
            win = self.window
            if win.winfo_ismapped():
                self.app._doc_window_last = (win.winfo_width(), win.winfo_height(), win.winfo_x(), win.winfo_y())
        except tk.TclError:
            pass

    # --- the buttons, the line numbers and the shortcuts (2026-10-30) ----
    # うにさん「別ウインドウにも行番号を付け、ボタンメニューを並べる。文字を引用モードで引用したり、
    # 括弧で括る、再変換をボタンとショートカットでできるようにする」. The actions are the main window's own:
    # this window's cursor and selection are handed to the memo (the same text while a peer), the action
    # runs there, and the cursor and selection come back here. While the main window shows another tab, it
    # goes to this tab first (as Ctrl+S does).
    BRACKETS = (('（', '）'), ('「', '」'), ('『', '』'), ('【', '】'), ('“', '”'))

    def _build_toolbar(self):
        app = self.app
        editor = app.editor
        try:
            bg, fg = editor.cget('bg'), editor.cget('fg')
        except tk.TclError:
            bg, fg = None, None
        look = dict(relief='flat', bd=1, font=('Yu Gothic UI', 9), pady=2, cursor='hand2')
        if bg is not None:
            look.update(bg=bg, fg=fg)
        bar = self.toolbar = tk.Frame(self.window, bg=bg) if bg is not None else tk.Frame(self.window)
        bar.pack(side='top', fill='x')
        self.buttons = {}

        def add(key, text, command, hint):
            button = tk.Button(bar, text=text, command=command, padx=8, **look)
            button.pack(side='left', padx=(4, 0), pady=2)
            self.buttons[key] = button
            button.bind('<Enter>', lambda e: self._hint(hint), add=True)
            button.bind('<Leave>', lambda e: self._hint(''), add=True)
        add('reconvert', '再変換', self.reconvert, '【再変換】カーソルの前の語の候補を出します。ショートカットキー：F5')
        add('quote', 'クリックして引用', self.quote,
            '【引用】本体の欄の語や行をクリックすると、この窓のカーソルの位置へ引用します。ショートカットキー：F1')
        for count, (open_ch, close_ch) in enumerate(self.BRACKETS, 1):
            add('bracket_%d' % count, open_ch + close_ch,
                lambda o=open_ch, c=close_ch: self.bracket(o, c),
                '選択中の文字や、変換中の文字を括弧で包みます。ショートカットキー：F2'
                + ('を%d回' % count if count > 1 else ''))

    def _hint(self, text):
        try:
            self.app.status.config(text=text)
        except Exception:
            pass

    def _to_peer(self):
        """This tab in the memo, and this window its peer (the main window goes to the tab if needed)."""
        if self.mode != 'peer':
            app = self.app
            index = next((i for i, t in enumerate(app.session.tabs) if t is self.tab), None)
            if index is None:
                return False
            app._switch_tab(index)
            self.show()
        return self.mode == 'peer' and self.text is not None

    def _hand_to_memo(self):
        """The memo takes this window's cursor and selection (each peer has its own)."""
        peer, editor = self.text, self.app.editor
        editor.mark_set('insert', peer.index('insert'))
        editor.tag_remove('sel', '1.0', 'end')
        selected = peer.tag_ranges('sel')
        if selected:
            editor.tag_add('sel', selected[0], selected[1])

    def _take_back(self, focus=True):
        peer, editor = self.text, self.app.editor
        if self.mode != 'peer' or peer is None:
            return
        try:
            peer.mark_set('insert', editor.index('insert'))
            peer.tag_remove('sel', '1.0', 'end')
            selected = editor.tag_ranges('sel')
            if selected:
                peer.tag_add('sel', selected[0], selected[1])
            peer.see('insert')
            if focus:
                peer.focus_set()
        except tk.TclError:
            pass

    def _run(self, action, focus_back=True):
        if not self._to_peer():
            return 'break'
        try:
            self._hand_to_memo()
            action()
        except Exception:
            import traceback
            traceback.print_exc()
        self.app.root.after_idle(lambda: self._take_back(focus_back))
        return 'break'

    def _event(self, keysym, state=0):
        from types import SimpleNamespace
        return SimpleNamespace(widget=self.app.editor, keysym=keysym, char='', state=state, keycode=0,
                               x_root=0, y_root=0)

    def bracket(self, open_ch, close_ch):
        app = self.app
        if (open_ch, close_ch) == ('（', '）'):
            return self._run(lambda: app._wrap_with_parens(widget=app.editor))
        return self._run(lambda: app._wrap_with_brackets(open_ch, close_ch, widget=app.editor))

    def reconvert(self):
        # The candidate list opens over the memo and takes the focus (as the main window's button)
        return self._run(lambda: self.app._on_f2_candidates(self._event(self.app.CANDIDATE_KEY)), focus_back=False)

    def quote(self):
        # The words and rows are clicked in the main window's panes; they go to this window's cursor
        return self._run(lambda: self.app.toggle_pick_mode(calculate=True), focus_back=False)

    def _bind_keys(self, text):
        app = self.app
        for key in ('F1', app.BRACKET_KEY, app.CANDIDATE_KEY):
            text.bind('<%s>' % key, lambda e, k=key: self.on_key(k, e.state))

    def on_key(self, keysym, state=0):
        """F1 (quote), F2 (brackets), F5 (candidates) in this window: the main window's own handlers, on this
        window's cursor and selection."""
        app = self.app
        event = self._event(keysym, state)
        if keysym == app.BRACKET_KEY:
            return self._run(lambda: app._on_f5_brackets(event))
        if keysym == app.CANDIDATE_KEY:
            return self._run(lambda: app._on_f2_candidates(event), focus_back=False)
        return self._run(lambda: app._on_pick_key(event), focus_back=False)

    def _place_gutter(self, text):
        """Line numbers left of the text, as in the main window (the memo's bookmarks while a peer)."""
        if self.gutter is not None:
            try:
                self.gutter.destroy()
            except tk.TclError:
                pass
            self.gutter = None
        try:
            app_module = _app_module(self.app)
            peer = self.mode == 'peer'
            # A peer's commands go to the memo (route_edits), which has its own watchers: the line numbers follow
            # its scrolling and keys instead of wrapping its command once more
            if peer and getattr(text, '_correctnote_observers', None) is None:
                text._correctnote_observers = {}
            gutter = app_module.LineNumberGutter(
                self.body, text, bookmarks=getattr(self.app, 'bookmarks', None) if peer else set(),
                on_toggle_bookmark=getattr(self.app, '_toggle_bookmark', None) if peer else None)
            try:
                gutter.configure(bg=app_module.LINE_NUM_BG)
            except tk.TclError:
                pass
            gutter.pack(side='left', fill='y', before=text)
            self.gutter = gutter
            for sequence in ('<KeyRelease>', '<ButtonRelease-1>', '<Configure>'):
                text.bind(sequence, lambda e: self._redraw_gutter(), add=True)
        except Exception:
            import traceback
            traceback.print_exc()
            self.gutter = None

    def _redraw_gutter(self):
        gutter = self.gutter
        if gutter is None or getattr(self, '_gutter_job', None) is not None:
            return
        def run():
            self._gutter_job = None
            try:
                gutter.redraw()
            except tk.TclError:
                pass
        try:
            self._gutter_job = self.window.after_idle(run)
        except tk.TclError:
            self._gutter_job = None

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
        self._bind_keys(text)
        try:
            import mouse_words              # 右を押しながら左・ダブルクリックで語（2026-10-30）
            mouse_words.install(self.app, text)
        except Exception:
            pass
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
        self.paint_peer()
        self._redraw_gutter()

    def paint_peer(self):
        """While a peer: the memo's painter gives the rows in this window's view their part-of-speech
        sizes and colours (it paints only the memo's own view・2026-10-30)."""
        if self.mode != 'peer' or getattr(self, '_paint_job', None) is not None:
            return
        try:
            self._paint_job = self.window.after_idle(self._paint_peer_now)
        except tk.TclError:
            self._paint_job = None

    def _paint_peer_now(self):
        self._paint_job = None
        rows = self.visible_rows()
        if rows is None:
            return
        try:
            from boundary_colors import paint_view
            paint_view(self.app, self.app.editor, rows[0] + 1 - 8, rows[1] + 1 + 8)
        except Exception:
            pass

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
        if self.gutter is not None:
            try:
                self.gutter.configure(bg=_app_module(self.app).LINE_NUM_BG)
                self.gutter.redraw()
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
        self._place_gutter(peer)
        peer.bind('<KeyRelease>', lambda e: self.app._on_change(), add=True)
        peer.bind('<FocusIn>', lambda e: self.app._queue_doc_window_priority(), add=True)
        peer.bind('<MouseWheel>', lambda e: self.app.root.after_idle(self.app._queue_doc_window_priority), add=True)
        peer.bind('<Map>', lambda e: self.paint_peer(), add=True)
        self._go_to_line(top)
        self.paint_peer()

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
        self._place_gutter(box)
        # Its own painter: the part-of-speech sizes and colours from the analysis already made for these rows
        # (2026-10-30 うにさん「品詞ごとの書式が反映されていないことが多い」。the copy had none)
        try:
            from boundary_colors import install
            install(self.app, box)
        except Exception:
            pass
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
        self._remember_place()
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        windows = getattr(self.app, '_doc_windows', None)
        if windows is not None and self in windows:
            windows.remove(self)
