# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Insert at a character boundary in each selected logical line."""
import tkinter as tk


def insertion_offsets(selected, distance, from_end=False):
    """Offsets refer to the original selection; a trailing newline excludes the next row."""
    if type(distance) is not int or distance < 0:
        raise ValueError('位置には0以上の整数を指定してください。')
    if not selected:
        return [], 0
    lines = selected.split('\n')
    if selected.endswith('\n'):
        lines.pop()
    offsets = []; cursor = 0; clamped = 0
    for line in lines:
        position = min(distance, len(line))
        offsets.append(cursor + (len(line)-position if from_end else position))
        clamped += distance > len(line)
        cursor += len(line)+1
    return offsets, clamped


class BulkInsertDialog:
    def __init__(self, app, colors):
        self.app = app
        self.colors = colors
        self.window = None
        self._undo_records = []
        self._undo_identity = None
        self._preview_job = None
        self._preview_markers = []
        self._preview_points = []
        self._preview_bindings = []

    def open(self):
        if self.window is not None:
            self.window.deiconify(); self.window.lift(); self.text.focus_set()
            return
        panel, ink, accent = self.colors()
        win = self.window = tk.Toplevel(self.app.root)
        win.withdraw(); win.title('一括挿入'); win.configure(bg=panel)
        win.transient(self.app.root)
        win.resizable(True, False)
        self.app._set_window_icons_win32(win)
        body = tk.Frame(win, bg=panel); body.pack(fill='both', expand=True, padx=14, pady=12)
        self.direction = tk.StringVar(win, self.app.settings.get('bulk_insert_direction'))
        if self.direction.get() not in ('start', 'end'):self.direction.set('start')
        self.distance = tk.StringVar(win, self.app.settings.get('bulk_insert_distance'))
        row = tk.Frame(body, bg=panel); row.pack(fill='x')
        for label, value in (('先頭から', 'start'), ('末尾から', 'end')):
            tk.Radiobutton(row, text=label, variable=self.direction, value=value,
                bg=panel, fg=ink, selectcolor=panel, activebackground=panel,
                activeforeground=ink).pack(side='left')
        self.position = tk.Spinbox(row, textvariable=self.distance, width=6,
                                 from_=0, to=2147483647, increment=1, wrap=False,
                                 buttonbackground=panel,
                                 exportselection=False, bg=panel, fg=ink, insertbackground=ink,
                                 selectbackground=accent, selectforeground=ink)
        self.position.pack(side='left', padx=(8, 0))
        self.position_choices = tk.Menubutton(row, text='▾', bg=panel, fg=ink,
            relief='raised', activebackground=panel, activeforeground=ink)
        self.position_choices.pack(side='left', padx=(0, 4))
        self.position_menu = tk.Menu(self.position_choices, tearoff=False,
            bg=panel, fg=ink, activebackground=accent, activeforeground=ink,
            postcommand=self._update_position_menu)
        self.position_choices.configure(menu=self.position_menu)
        self.unit = tk.Label(row, bg=panel, fg=ink)
        self.unit.pack(side='left')
        def update_unit(*args):
            self.unit.config(text='文字前' if self.direction.get()=='end' else '文字後')
        self.direction.trace_add('write', update_unit); update_unit()
        tk.Label(body, text='0は指定側の端、文字数を超える値は反対側の端に挿入します。',
                 bg=panel, fg=ink, anchor='w').pack(fill='x', pady=(4, 10))
        tk.Label(body, text='挿入する文字列', bg=panel, fg=ink, anchor='w').pack(fill='x')
        self.text = tk.Text(body, width=38, height=3, wrap='char', undo=True,
                            exportselection=False, bg=panel, fg=ink, insertbackground=ink,
                                 selectbackground=accent, selectforeground=ink)
        self.text.pack(fill='x', pady=(4, 8))
        self.text.insert('1.0', self.app.settings.get('bulk_insert_text') or '')
        self.message = tk.Label(body, text='本文の選択部分を行ごとに処理します。縦線が挿入位置です。',
                                bg=panel, fg=ink, anchor='w', wraplength=400)
        self.message.pack(fill='x', pady=(0, 8))
        buttons = tk.Frame(body, bg=panel); buttons.pack(fill='x')
        self.execute = tk.Button(buttons, text='実行', command=self.apply,
                                  bg=accent, fg=panel, activebackground=accent,
                                  activeforeground=panel, padx=18)
        self.execute.pack(side='left')
        self.undo_button = tk.Button(buttons, text='実行を戻す', command=self.undo,
                                     state='disabled')
        self.undo_button.pack(side='left', padx=8)
        self.close_button = tk.Button(buttons, text='閉じる（Esc）', command=self.close)
        self.close_button.pack(side='left')
        editor = self.app.editor
        self._selection_style = (editor.cget('inactiveselectbackground'),
                                 editor.cget('exportselection'))
        editor.configure(inactiveselectbackground=editor.cget('selectbackground'),
                         exportselection=False)
        win.protocol('WM_DELETE_WINDOW', self.close)
        win.bind('<Escape>', self.close)
        win.update_idletasks()
        self.app._place_dialog(win,win.winfo_reqwidth(),win.winfo_reqheight())
        self._start_preview()
        win.deiconify(); self.text.focus_set()
        self.queue_preview()

    def _start_preview(self):
        self._preview_traces = [(var, var.trace_add('write', self.queue_preview))
                                for var in (self.direction, self.distance)]
        for widget, sequences in ((self.window, ('<FocusIn>', '<FocusOut>')),
                (self.app.editor, ('<<Selection>>', '<Configure>', '<FocusIn>', '<FocusOut>'))):
            for sequence in sequences:
                ident = widget.bind(sequence, self.queue_preview, add=True)
                self._preview_bindings.append((widget, sequence, ident))

    def queue_preview(self, *args):
        if self.window is not None and self._preview_job is None:
            self._preview_job = self.app.root.after_idle(self._draw_preview)

    def _hide_preview(self):
        self._preview_points = []
        for marker in self._preview_markers:
            marker.place_forget()

    def _forward_preview_mouse(self, event, sequence):
        editor = self.app.editor
        options = dict(x=event.x_root-editor.winfo_rootx(),
                       y=event.y_root-editor.winfo_rooty(), state=event.state)
        if sequence == '<MouseWheel>':
            options['delta'] = event.delta
        else:
            self._hide_preview()
            editor.focus_set()
        editor.event_generate(sequence, **options)
        return 'break'

    def _draw_preview(self):
        self._preview_job = None
        self._hide_preview()
        if self.window is None:
            return
        focus = self.app.root.focus_get()
        if focus is None or not (focus is self.window or
                str(focus).startswith(str(self.window) + '.')):
            return
        value = self.distance.get().strip()
        if not value or not value.isdecimal():
            return
        editor = self.app.editor
        ranges = editor.tag_ranges('sel')
        if not ranges:
            return
        from app import _stable_text_index
        first, last = (_stable_text_index(editor,i) for i in (ranges[0], ranges[-1]))
        offsets, unused = insertion_offsets(editor.get(first,last), int(value),
                                            self.direction.get() == 'end')
        width, height = editor.winfo_width(), editor.winfo_height()
        top = int(editor.index('@0,0').split('.')[0])
        bottom = int(editor.index('@%d,%d' % (width,height)).split('.')[0])
        first_row = int(editor.index(first).split('.')[0])
        color = self.colors()[2]
        for row, offset in enumerate(offsets, first_row):
            if row < top or row > bottom:
                continue
            index = f'{first}+{offset}c'
            box = editor.bbox(index)
            if box is None:
                continue
            x, y, unused_width, line_height = box
            if x < 0 or x >= width or y + line_height <= 0 or y >= height:
                continue
            number = len(self._preview_points)
            if number == len(self._preview_markers):
                marker = tk.Frame(editor, bg=color, bd=0, takefocus=False, cursor='xterm')
                for sequence in ('<ButtonPress-1>', '<ButtonPress-3>', '<MouseWheel>'):
                    marker.bind(sequence, lambda e, seq=sequence:self._forward_preview_mouse(e,seq))
                self._preview_markers.append(marker)
            marker = self._preview_markers[number]
            marker.configure(bg=color)
            marker.place(x=max(0,x-1), y=y, width=2, height=line_height, bordermode='outside')
            marker.lift()
            self._preview_points.append((index,x,y,line_height))

    def _stop_preview(self):
        if self._preview_job is not None:
            self.app.root.after_cancel(self._preview_job)
            self._preview_job = None
        for variable, ident in self._preview_traces:
            variable.trace_remove('write', ident)
        for widget, sequence, ident in self._preview_bindings:
            widget.unbind(sequence, ident)
        self._preview_bindings.clear()
        for marker in self._preview_markers:
            marker.destroy()
        self._preview_markers.clear(); self._preview_points.clear()

    def _update_position_menu(self):
        value = self.distance.get().strip()
        current = int(value) if value.isdecimal() else 0
        start = max(0, current - 10)
        self.position_menu.delete(0, 'end')
        # Keep a small menu at any directly entered position, in steps of one.
        for number in range(start, start + 21):
            self.position_menu.add_command(label=str(number),
                command=lambda n=number: self.distance.set(str(n)))

    def save(self):
        if self.window is None:return
        values = {'bulk_insert_text':self.text.get('1.0','end-1c'),
                  'bulk_insert_direction':self.direction.get(),
                  'bulk_insert_distance':self.distance.get()}
        for name, value in values.items():self.app.settings.set(name,value)
        self.app.settings.save()

    def close(self, event=None, focus=True):
        if self.window is None:return None
        self.save()
        self._stop_preview()
        win = self.window; self.window = None; win.destroy()
        color, exported = self._selection_style
        self.app.editor.configure(inactiveselectbackground=color, exportselection=exported)
        self._undo_records.clear(); self._undo_identity = None
        if focus:self.app.editor.focus_set()
        return 'break'

    def _edit_identity(self):
        import analysis_work_app as work
        editor = self.app.editor
        # Compare only at a bulk operation, never poll or retain the document.
        return work.token(self.app), hash(editor.get('1.0', 'end-1c'))

    def undo(self):
        import ime_watch
        editor = self.app.editor
        if any(ime_watch.composition_active(w.winfo_id()) for w in (editor,self.text)):
            self.message.config(text='変換中の文字を確定してから戻してください。'); return
        if not self._undo_records:
            return
        if self._edit_identity() != self._undo_identity:
            self._undo_records.clear(); self._undo_identity = None
            self.undo_button.config(state='disabled')
            self.message.config(text='本文の編集やタブ切替後は、このボタンでは戻せません。'); return
        first, last = self._undo_records[-1]
        try:
            editor.edit_undo()
        except tk.TclError:
            self._undo_records.clear(); self._undo_identity = None
            self.undo_button.config(state='disabled')
            self.message.config(text='この実行を戻す履歴がありません。'); return
        self._undo_records.pop()
        editor.tag_remove('sel','1.0','end')
        editor.tag_add('sel',first,last)
        self.app._after_ime_char_insert(editor)
        self._undo_identity = self._edit_identity()
        self.undo_button.config(state='normal' if self._undo_records else 'disabled')
        self.message.config(text='直前の一括挿入を戻しました。')

    def apply(self):
        from app import _stable_text_index
        from text_edit import undo_group
        import ime_watch
        self.save()
        editor = self.app.editor
        if any(ime_watch.composition_active(w.winfo_id()) for w in (editor,self.text)):
            self.message.config(text='変換中の文字を確定してから実行してください。'); return
        value = self.distance.get().strip()
        if not value or not value.isdecimal():
            self.message.config(text='位置には0以上の整数を指定してください。'); return
        distance = int(value)
        ranges = editor.tag_ranges('sel')
        if not ranges:
            self.message.config(text='本文で挿入対象の範囲を選択してください。'); return
        first, last = (_stable_text_index(editor,index) for index in (ranges[0],ranges[-1]))
        selected = editor.get(first,last)
        insertion = self.text.get('1.0','end-1c')
        offsets, clamped = insertion_offsets(selected,distance,self.direction.get()=='end')
        if not insertion:
            self.message.config(text='挿入する文字列を入力してください。'); return
        if not offsets:
            self.message.config(text='本文で挿入対象の範囲を選択してください。'); return
        if self._edit_identity() != self._undo_identity:
            self._undo_records.clear()
        self.app._forget_bracket_cycle()
        if getattr(self.app,'_pick_mode',None):self.app._end_pick_mode(keep_equals=True)
        with undo_group(editor):
            for offset in reversed(offsets):editor.insert(f'{first}+{offset}c',insertion)
            editor.tag_remove('sel','1.0','end')
            editor.tag_add('sel',first,f'{first}+{len(selected)+len(insertion)*len(offsets)}c')
        self.app._after_ime_char_insert(editor)
        self._undo_records.append((first,last))
        self._undo_identity = self._edit_identity()
        self.undo_button.config(state='normal')
        suffix = f'（{clamped}行は選択部分の端に挿入）' if clamped else ''
        self.message.config(text=f'{len(offsets)}行に挿入しました。'+suffix)
