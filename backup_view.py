# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""A window showing one tab backup (tab_backup), to read and copy from (2026-10-23 うにさん
「バックアップの窓は見るだけ（編集不可、選択とコピーは可）。窓の中に『このバックアップを削除する』
ボタン、確認ダイアログのあと、その1つだけ消す」).

The text box stays a normal Text (it takes the focus, so the selection and Ctrl+C work), and its
Tcl command refuses every change once the backup is in it.
"""
import tkinter as tk
from tkinter import messagebox


def make_read_only(text):
    """Refuse insert/delete/replace on this Text from now on (typing, pasting, cutting, IME).

    A Tcl procedure, not a Python command (2026-10-23 うにさん「バックアップウインドウ表示中に、ダークモード
    切替するとアプリがクラッシュする」): the theme switch asks every widget for options such as -selectcolor
    that a Text does not have. Through a Python command that error is kept by tkinter and raised again from
    mainloop(), which ended the app. Here the answer and the error go back to the caller as Tk's own."""
    real = text._w + '_backup_view'
    text.tk.call('rename', text._w, real)
    text.tk.call('proc', text._w, 'args',
                 'switch -- [lindex $args 0] {\n'
                 '    insert - delete - replace {return {}}\n'
                 '    edit {if {[lindex $args 1] in {undo redo}} {return {}}}\n'
                 '}\n'
                 'tailcall %s {*}$args' % real)

    def destroyed(event):
        if event.widget is text:
            try:
                text.tk.call('rename', text._w, '')
            except tk.TclError:
                pass
    text.bind('<Destroy>', destroyed, add=True)
    return real


class BackupWindow:
    FIND_TAG = 'bv_found'
    FIND_CURRENT_TAG = 'bv_found_current'
    FIND_EMPHASIS = 'emph_bvfind'
    FIND_LIMIT = 500                # marked at most (as the memo's search)

    def __init__(self, app, path, when, tab_title, colors, font, remove, manual=False, select=None,
                 geometry=None, on_view=None, find=None):
        """remove(path) deletes the backup file; True when it is gone. manual: made from the File menu.
        select: (background, foreground) of the selection — the memo's (2026-10-23 うにさん「範囲選択の色が
        濃すぎる」). geometry: the window's size and place when it opens. on_view(): the view moved or was
        resized (the space marks are painted again). find: the search bar's looks, as callables so that a
        theme switch is followed — colors() → (found, current), factor() → the letters' size,
        field() → (bg, fg), tab_colors() → MarkedEntry's tab marks."""
        panel, ink, accent = colors
        select_bg, select_fg = select or (accent, panel)
        self.app, self.path, self._remove = app, path, remove
        win = self.window = tk.Toplevel(app.root)
        kind = '手動のバックアップ' if manual else 'バックアップ'
        win.title('%s — %s — %s' % (kind, tab_title, when.strftime('%Y/%m/%d %H:%M')))
        win.configure(bg=panel)
        if geometry:
            win.geometry(geometry)                  # 2026-10-23 うにさん「開いた時点で今よりも大きくする」
        try:
            app._set_window_icons_win32(win)
        except Exception:
            pass
        top = tk.Frame(win, bg=panel)
        top.pack(side='top', fill='x', padx=10, pady=(8, 4))
        tk.Label(top, text='%s に%sバックアップ（見るだけ・選んでコピーできます）'
                 % (when.strftime('%Y/%m/%d %H:%M'), '手動で作った' if manual else '保存した'),
                 bg=panel, fg=ink).pack(side='left')
        self.delete_button = tk.Button(top, text='このバックアップを削除する', command=self.ask_delete,
                                       bg=panel, fg=ink, relief='groove', padx=8)
        self.delete_button.pack(side='right')
        # The search bar, always there (2026-10-23 うにさん「バックアップウインドウに専用の検索欄を設ける。
        # 別ウインドウで出さず、入力欄が置いてある」): each letter typed searches this window's text; the hits
        # look as the memo's search (the same colours, the letters larger); Enter / Shift+Enter or ▼ ▲ go to
        # the next / previous; Ctrl+F comes here. 2026-10-24 うにさん: the field looks like a field (its own
        # background and a 1px border, light and dark); × empties it; Esc takes the marks away and keeps the
        # words; the window does not close with Esc — Ctrl+W closes it (not the main window's tab)
        self._find = find or {}
        self._spans = []
        self._current = None
        self._build_find_bar(win, panel, ink)
        body = tk.Frame(win, bg=panel)
        body.pack(side='top', fill='both', expand=True, padx=10, pady=(0, 10))
        self.text = tk.Text(body, wrap='word', bg=panel, fg=ink, insertbackground=ink, font=font,
                            relief='flat', padx=10, pady=8, undo=False, width=80, height=24,
                            selectbackground=select_bg, selectforeground=select_fg,
                            inactiveselectbackground=select_bg)
        bar = tk.Scrollbar(body, command=self.text.yview)

        def scrolled(*args):
            bar.set(*args)
            if on_view is not None:
                on_view()
        self.text.configure(yscrollcommand=scrolled)
        if on_view is not None:
            self.text.bind('<Configure>', lambda e: on_view(), add=True)
        # Colour emoji as in the memo (emoji_color・2026-10-23 うにさん「絵文字に色がないので塗る」). Before the
        # text goes in and before the read-only wrapper (which sits on top of the emoji's watcher)
        try:
            from emoji_color import install as install_emoji_color
            install_emoji_color(self.text)
        except Exception:
            pass
        bar.pack(side='right', fill='y')
        self.text.pack(side='left', fill='both', expand=True)
        import tab_backup
        try:
            content = tab_backup.read(path)
        except OSError as error:
            content = 'このバックアップを読めませんでした: %s' % error
        self.text.insert('1.0', content)
        self.text.mark_set('insert', '1.0')
        make_read_only(self.text)
        self.refresh_find_colors()
        win.bind('<Escape>', self._find_escape)
        # this window's Ctrl+W comes before the main window's (bind_all): 'break'
        win.bind('<Control-w>', self._close_key)
        win.bind('<Control-W>', self._close_key)
        win.bind('<Control-f>', self.focus_find)
        win.bind('<Control-F>', self.focus_find)
        self.text.focus_set()

    # --- the search bar ---------------------------------------------------------------------------
    def _build_find_bar(self, win, panel, ink):
        from marked_entry import MarkedEntry
        bar = self.find_bar = tk.Frame(win, bg=panel)
        bar.pack(side='top', fill='x', padx=10, pady=(0, 6))
        tk.Label(bar, text='検索', bg=panel, fg=ink).pack(side='left', padx=(0, 6))
        self.find_var = tk.StringVar(win)
        tab_colors = self._find.get('tab_colors') or (lambda: ('#d8d8d8', '#c8c8c8'))
        self.find_entry = MarkedEntry(bar, textvariable=self.find_var, tab_colors=tab_colors, width=30,
                                      exportselection=False, font=('Yu Gothic UI', 10), relief='flat',
                                      highlightthickness=1)
        self._field_look(panel, ink)
        self.find_entry.pack(side='left', ipady=3)
        self.find_clear = tk.Button(bar, text='×', command=self.clear_find_field, bg=panel, fg=ink,
                                    relief='flat', padx=6)
        self.find_clear.pack(side='left', padx=(6, 0))
        self.find_prev = tk.Button(bar, text='▲', command=lambda: self.find_step(-1), bg=panel, fg=ink,
                                   relief='flat', padx=6)
        self.find_next = tk.Button(bar, text='▼', command=lambda: self.find_step(1), bg=panel, fg=ink,
                                   relief='flat', padx=6)
        self.find_prev.pack(side='left')
        self.find_next.pack(side='left')
        self.find_count = tk.Label(bar, text='', bg=panel, fg=ink)
        self.find_count.pack(side='left', padx=(8, 0))
        self.find_var.trace_add('write', lambda *args: self.search())
        self.find_entry.bind('<Return>', lambda e: (self.find_step(1), 'break')[1])
        self.find_entry.bind('<Shift-Return>', lambda e: (self.find_step(-1), 'break')[1])
        self.find_entry.bind('<Escape>', self._find_escape)

    def focus_find(self, event=None):
        self.find_entry.focus_set()
        try:
            self.find_entry.select_range(0, 'end')
        except tk.TclError:
            pass
        return 'break'

    def _field_look(self, panel=None, ink=None):
        """The field's own background and 1px border (field() → (bg, fg[, border, border with the focus]))."""
        look = tuple((self._find.get('field') or (lambda: (panel, ink)))())
        bg, fg = look[0], look[1]
        border = look[2] if len(look) > 2 else fg
        focus = look[3] if len(look) > 3 else border
        try:
            self.find_entry.configure(bg=bg, fg=fg, insertbackground=fg, highlightbackground=border,
                                      highlightcolor=focus)
        except tk.TclError:
            pass

    def _find_escape(self, event=None):
        """Esc: the marks go, the words stay in the field. The window stays (Ctrl+W closes it)."""
        if self._spans or self.find_count.cget('text'):
            self._clear_find()
            self._spans, self._current = [], None
            self.find_count.config(text='')
        return 'break'

    def clear_find_field(self):
        """×: the field is emptied and the marks go."""
        self.find_var.set('')
        self.find_entry.focus_set()

    def _close_key(self, event=None):
        self.close()
        return 'break'

    def refresh_find_colors(self):
        """The hit colours (the memo's search) and the field — again after a theme switch."""
        self._field_look()
        found, current = (self._find.get('colors') or (lambda: ('#ffe9a8', '#ffc95c')))()
        try:
            self.text.tag_configure(self.FIND_TAG, background=found)
            self.text.tag_configure(self.FIND_CURRENT_TAG, background=current)
            self.text.tag_raise(self.FIND_TAG)
            self.text.tag_raise(self.FIND_CURRENT_TAG)
            self.text.tag_raise('sel')
        except tk.TclError:
            pass

    def _clear_find(self):
        import emphasis_font
        try:
            self.text.tag_remove(self.FIND_TAG, '1.0', 'end')
            self.text.tag_remove(self.FIND_CURRENT_TAG, '1.0', 'end')
            emphasis_font.clear(self.text, self.FIND_EMPHASIS)
        except tk.TclError:
            pass

    def search(self):
        """Search this window's text for the field's words — plain text, not a regular expression, any
        letter case (as the memo's search by default) — and mark every hit; the current one is the first
        from the top of the view."""
        import emphasis_font
        import search as searchlib
        self._clear_find()
        self._spans, self._current = [], None
        query = self.find_var.get()
        if not query:
            self.find_count.config(text='')
            return []
        try:
            pattern = searchlib.build_pattern(query, regex=False, match_case=False, whole_word=False)
            content = self.text.get('1.0', 'end-1c')
            spans = list(searchlib.find_all(content, pattern)) if pattern is not None else []
        except Exception:
            spans = []
        self._spans = spans
        if not spans:
            self.find_count.config(text='見つかりません')
            return spans
        factor = (self._find.get('factor') or (lambda: 1.3))()
        for start, end in spans[:self.FIND_LIMIT]:
            first, last = '1.0+%dc' % start, '1.0+%dc' % end
            self.text.tag_add(self.FIND_TAG, first, last)
            try:
                emphasis_font.apply(self.text, first, last, factor, self.FIND_EMPHASIS)
            except tk.TclError:
                pass
        try:
            top = len(self.text.get('1.0', '@0,0'))
        except tk.TclError:
            top = 0
        self._current = next((i for i, (start, _end) in enumerate(spans) if start >= top), 0)
        self._show_current()
        return spans

    def find_step(self, step):
        if not self._spans:
            if self.find_var.get():
                self.search()
            return
        self._current = ((self._current or 0) + step) % len(self._spans)
        self._show_current()

    def _show_current(self):
        start, end = self._spans[self._current]
        first, last = '1.0+%dc' % start, '1.0+%dc' % end
        try:
            self.text.tag_remove(self.FIND_CURRENT_TAG, '1.0', 'end')
            self.text.tag_add(self.FIND_CURRENT_TAG, first, last)
            self.text.see(first)
            self.text.mark_set('insert', first)
        except tk.TclError:
            pass
        self.find_count.config(text='%d／%d 件' % (self._current + 1, len(self._spans)))

    def ask_delete(self):
        if not messagebox.askyesno('バックアップを削除する',
                                   'このバックアップを削除しますか？\n（このバックアップ1つだけを消します。'
                                   'タブの本文やほかのバックアップは消えません）',
                                   parent=self.window):
            return False
        if self._remove(self.path):
            self.close()
            return True
        messagebox.showerror('バックアップを削除する', '削除できませんでした。', parent=self.window)
        return False

    def close(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass
