# -*- coding: utf-8 -*-
"""Toolbar presentation preferences and the corresponding F5 order."""

BUTTONS = (
    ('first', '1行目', 'first_line_btn'),
    ('last', '最終行', 'last_line_btn'),
    ('bookmark_previous', '▲ 前のブックマーク', 'bookmark_prev_btn'),
    ('bookmark_next', '▼ 次のブックマーク', 'bookmark_next_btn'),
    ('quote', 'クリックして引用', 'pick_mode_btn'),
    ('list', '箇条書き', 'list_mode_btn'),
    ('quick', '簡易入力', 'quick_input_btn'),
    ('word_book', '単語帳', 'word_book_btn'),
    ('bulk_insert', '一括挿入', 'bulk_insert_btn'),
    ('ruler', 'ルーラー', 'ruler_btn'),
    ('bracket_parens', '（）', 0),
    ('bracket_single', '「」', 1),
    ('bracket_double', '『』', 2),
    ('bracket_black', '【】', 3),
    ('bracket_quotes', '“”', 4),
    ('layout_split', '左右に並べる', 'layout_split_btn'),
    ('layout_unified', '1つにまとめる', 'layout_unified_btn'),
)
IDS = tuple(item[0] for item in BUTTONS)
LABELS = {key: label for key, label, _ in BUTTONS}
BRACKET_KINDS = {key: attr for key, _, attr in BUTTONS if type(attr) is int}
LAYOUT_KEYS = ('layout_split','layout_unified')

def configuration_order(order):
    return [key for key in order if key!='layout_unified']

def label_for(key):
    return '左右に並べる／1つにまとめる' if key=='layout_split' else LABELS[key]


def normalized(order=None, hidden=None):
    """Ignore invalid entries, keep a saved order, append newly added buttons."""
    result = []
    if isinstance(order, (tuple, list)):
        for key in order:
            if isinstance(key, str) and key in IDS and key not in result:
                result.append(key)
    result.extend(key for key in IDS if key not in result)
    hidden = hidden if isinstance(hidden, (tuple, list, set, frozenset)) else ()
    hidden={key for key in hidden if isinstance(key,str) and key in IDS}
    position=min(result.index(key) for key in LAYOUT_KEYS)
    result=[key for key in result if key not in LAYOUT_KEYS]
    result[position:position]=LAYOUT_KEYS
    if hidden.intersection(LAYOUT_KEYS):hidden.update(LAYOUT_KEYS)
    return result,hidden


def bracket_order(order=None, hidden=None):
    order, hidden = normalized(order, hidden)
    return tuple(BRACKET_KINDS[key] for key in order
                 if key in BRACKET_KINDS and key not in hidden)


def next_bracket(kinds, current=None):
    if not kinds:
        return None
    return kinds[(kinds.index(current) + 1) % len(kinds)] if current in kinds else kinds[0]


class ToolbarPreferences:
    def __init__(self, app, palette):
        self.app, self.palette = app, palette
        self.order, self.hidden = normalized(app.settings.get('toolbar_order'),
                                             app.settings.get('toolbar_hidden'))
        self.widgets = {key: (app._bracket_buttons[attr] if type(attr) is int
                              else getattr(app, attr)) for key, _, attr in BUTTONS}
        self.pack_options = {key: dict(widget.pack_info()) for key, widget in self.widgets.items()}
        for options in self.pack_options.values():
            options.pop('in', None)
        app._toolbar_normal_padx = {widget: widget.winfo_pixels(widget.cget('padx'))
                                   for widget in self.widgets.values()}
        self.window = None
        self.variables = {}
        self._save_job=None
        self._hint_kinds=None
        self.refresh_menu()
        self.apply()

    def kinds(self):
        return bracket_order(self.order, self.hidden)

    def refresh_menu(self):
        import tkinter as tk
        menu = self.app._buttons_menu
        menu.delete(0, 'end')
        self.variables = {}
        menu.add_command(label='表示と並べ替え…', command=self.open)
        menu.add_separator()
        _, _, accent = self.palette()
        for key in configuration_order(self.order):
            variable = tk.BooleanVar(master=self.app.root, value=key not in self.hidden)
            self.variables[key] = variable
            menu.add_checkbutton(label=label_for(key), variable=variable, selectcolor=accent,
                command=lambda k=key, v=variable: self.set_visible(k, bool(v.get())))
        menu.add_separator()
        menu.add_command(label='初期の表示と順番に戻す', command=self.reset)

    def apply(self):
        toolbar = self.app._toolbar
        for key,widget in self.widgets.items():
            if key in self.hidden and widget.winfo_manager():widget.pack_forget()
        visible = [key for key in self.order if key not in self.hidden]
        # Keep the original right alignment only for a trailing layout group.
        split = len(visible)
        while split and visible[split-1].startswith('layout_'):
            split -= 1
        placement=[(key,'left') for key in visible[:split]]+[(key,'right') for key in reversed(visible[split:])]
        for index,(key,side) in enumerate(placement):
            widget=self.widgets[key];current=toolbar.pack_slaves()
            if index<len(current) and current[index] is widget and widget.pack_info()['side']==side:continue
            options=dict(self.pack_options[key],side=side)
            if index<len(current) and current[index] is not widget:options['before']=current[index]
            widget.pack(**options)
        if visible and not toolbar.winfo_manager():
            toolbar.pack(fill='x', padx=16, pady=(2, 6), after=self.app._tab_viewport)
        elif not visible:
            toolbar.pack_forget()
        kinds=self.kinds()
        for count, kind in enumerate(kinds if kinds!=self._hint_kinds else (), 1):
            hint = ('選択中の文字や、変換中の文字を括弧で包みます。ショートカットキー：F5'
                    + (f'を{count}回' if count > 1 else ''))
            button = self.app._bracket_buttons[kind]
            button.bind('<Enter>', lambda e, h=hint: self.app._toolbar_hover_hint(e, True, h))
            button.bind('<Leave>', lambda e, h=hint: self.app._toolbar_hover_hint(e, False, h))
        self._hint_kinds=kinds
        for key, variable in self.variables.items():
            variable.set(key not in self.hidden)
        self.app._queue_toolbar_fit()
        if self.window is not None:
            self.refresh_list()

    def save(self):
        self.app.settings.set('toolbar_order', list(self.order))
        self.app.settings.set('toolbar_hidden', [key for key in self.order if key in self.hidden])
        self.apply()
        if self._save_job is not None:self.app.root.after_cancel(self._save_job)
        self._save_job=self.app.root.after(180,self._flush_save)

    def _flush_save(self):
        if self._save_job is not None:self.app.root.after_cancel(self._save_job)
        self._save_job=None
        self.app.settings.save()

    def set_visible(self, key, visible):
        if key not in IDS:
            return
        keys=LAYOUT_KEYS if key in LAYOUT_KEYS else (key,)
        if all((k not in self.hidden)==visible for k in keys):return
        for k in keys:
            self.hidden.discard(k) if visible else self.hidden.add(k)
        self.save()

    def move(self, key, offset):
        if key not in self.order:
            return
        key='layout_split' if key in LAYOUT_KEYS else key
        grouped=configuration_order(self.order);index=grouped.index(key)
        target=max(0,min(len(grouped)-1,index+offset))
        if target!=index:
            grouped.insert(target,grouped.pop(index))
            self.order=[item for k in grouped for item in (LAYOUT_KEYS if k=='layout_split' else (k,))]
            self.refresh_menu()
            self.save()

    def reset(self):
        self.order, self.hidden = normalized()
        self.refresh_menu()
        self.save()

    def selected(self):
        indexes = self.listbox.curselection()
        return self._listed[indexes[0]] if indexes else None

    def refresh_list(self, select=None):
        selected = select or self.selected()
        self._listed=configuration_order(self.order)
        labels=[('☑ ' if key not in self.hidden else '☐ ')+label_for(key) for key in self._listed]
        # Update only changed rows; retaining the list avoids a full selection
        # and geometry rebuild on every click or one-position move.
        for index,label in enumerate(labels):
            if index>=self.listbox.size():self.listbox.insert('end',label)
            elif self.listbox.get(index)!=label:
                self.listbox.delete(index);self.listbox.insert(index,label)
        if selected in self._listed:
            index = self._listed.index(selected)
            self.listbox.selection_clear(0,'end')
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
        self.update_controls()

    def update_controls(self, event=None):
        key = self.selected()
        self.visible_var.set(key is not None and key not in self.hidden)
        self.check.configure(state='normal' if key else 'disabled')
        grouped=configuration_order(self.order)
        index=grouped.index(key) if key else -1
        self.up.configure(state='normal' if index > 0 else 'disabled')
        self.down.configure(state='normal' if 0 <= index < len(grouped)-1 else 'disabled')

    def toggle_selected(self, event=None):
        key = self.selected()
        if key:
            self.set_visible(key, key in self.hidden)
        return 'break'

    def click_checkbox(self,event):
        index=self.listbox.nearest(event.y);box=self.listbox.bbox(index)
        if box is None or not box[1]<=event.y<box[1]+box[3]:return
        import tkinter.font as tkfont
        width=tkfont.Font(root=self.window,font=self.listbox.cget('font')).measure('☑ ')
        if event.x>box[0]+width:return
        self.listbox.selection_clear(0,'end');self.listbox.selection_set(index)
        self.listbox.activate(index);self.listbox.focus_set()
        return self.toggle_selected()

    def move_selected(self, offset):
        key = self.selected()
        if key:
            self.move(key, offset)

    def open(self):
        import tkinter as tk
        if self.window is not None:
            self.window.deiconify(); self.window.lift(); self.listbox.focus_set()
            return
        panel, ink, accent = self.palette()
        window = self.window = tk.Toplevel(self.app.root)
        window.title('ボタンの表示と並べ替え')
        window.transient(self.app.root)
        window.configure(bg=panel)
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.bind('<Escape>', lambda e: self.close())
        tk.Label(window, text='表示するボタンと、左からの順番を変更します。\n変更はすぐに反映され、次回の起動にも残ります。',
                 bg=panel, fg=ink, justify='left').pack(anchor='w', padx=14, pady=(12, 8))
        body = tk.Frame(window, bg=panel);body.pack(fill='both', expand=True, padx=14)
        self.listbox = tk.Listbox(body, exportselection=False, width=30, height=17,
            bg=panel, fg=ink, selectbackground=accent, selectforeground=panel,
            highlightthickness=1)
        self.listbox.pack(side='left', fill='both', expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.update_controls)
        self.listbox.bind('<space>', self.toggle_selected)
        self.listbox.bind('<ButtonPress-1>',self.click_checkbox)
        controls = tk.Frame(body, bg=panel);controls.pack(side='left', fill='y', padx=(12, 0))
        self.visible_var = tk.BooleanVar(master=window)
        self.check = tk.Checkbutton(controls, text='表示する', variable=self.visible_var,
            command=lambda:self.set_visible(self.selected(), bool(self.visible_var.get())),
            bg=panel, fg=ink, selectcolor=panel, activebackground=panel, activeforeground=ink)
        self.check.pack(anchor='w', pady=(0, 14))
        def button(parent, label, command):
            return tk.Button(parent, text=label, command=command, bg=panel, fg=ink,
                             activebackground=accent, activeforeground=panel, padx=12, pady=4)
        self.up=button(controls, '上へ', lambda:self.move_selected(-1));self.up.pack(fill='x', pady=3)
        self.down=button(controls, '下へ', lambda:self.move_selected(1));self.down.pack(fill='x', pady=3)
        bottom=tk.Frame(window,bg=panel);bottom.pack(fill='x',padx=14,pady=12)
        button(bottom,'初期設定に戻す',self.reset).pack(side='left')
        button(bottom,'閉じる',self.close).pack(side='right')
        self._listed=[]
        self.refresh_list(select=self.order[0])
        self.listbox.focus_set()

    def close(self):
        if self._save_job is not None:self._flush_save()
        if self.window is not None:
            window, self.window = self.window, None
            window.destroy()
        return 'break'
