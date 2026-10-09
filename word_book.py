"""A user's explicitly collected phrases, separate from correction vocabulary."""
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont


def word_book_position(app_bounds, window_size, work_area, gap=6, number_left=None):
    """Outer-frame coordinates, including negative-coordinate monitors."""
    left, top, right, bottom = app_bounds
    width, height = window_size
    wl, wt, wr, wb = work_area
    x = left - width - gap
    if x < wl:
        # App chrome/empty gutter space may be covered; line numbers may not.
        edge = left if number_left is None else number_left
        x = wl if wl + width + 2 <= edge else min(right, wr) - width
    x = max(wl, min(x, max(wl, wr - width)))
    y = max(wt, min(top + 30, max(wt, wb - height)))
    return int(x), int(y)


class _WordBookNative:
    """Remember the preceding foreground window without polling or reading text."""
    def __init__(self, window, previous=None):
        import ctypes as c
        from ctypes import wintypes as W
        self.c = c
        self.user = u = c.WinDLL('user32', use_last_error=True)
        self.comctl = cc = c.WinDLL('comctl32', use_last_error=True)
        self.proc_type = c.WINFUNCTYPE(c.c_ssize_t, W.HWND, W.UINT,
                                      c.c_size_t, c.c_ssize_t, c.c_size_t, c.c_size_t)
        signatures = {
            'GetAncestor': ([W.HWND, W.UINT], W.HWND),
            'GetForegroundWindow': ([], W.HWND),
            'ReleaseCapture': ([], W.BOOL),
            'PostMessageW': ([W.HWND, W.UINT, c.c_size_t, c.c_ssize_t], W.BOOL),
            'GetWindowThreadProcessId': ([W.HWND, c.POINTER(W.DWORD)], W.DWORD),
            'IsWindow': ([W.HWND], W.BOOL), 'IsWindowVisible': ([W.HWND], W.BOOL),
            'IsIconic': ([W.HWND], W.BOOL), 'SetForegroundWindow': ([W.HWND], W.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(u, name); fn.argtypes = args; fn.restype = result
        for name, args, result in (
            ('SetWindowSubclass', [W.HWND, self.proc_type, c.c_size_t, c.c_size_t], W.BOOL),
            ('RemoveWindowSubclass', [W.HWND, self.proc_type, c.c_size_t], W.BOOL),
            ('DefSubclassProc', [W.HWND, W.UINT, c.c_size_t, c.c_ssize_t], c.c_ssize_t)):
            fn = getattr(cc, name); fn.argtypes = args; fn.restype = result
        self.hwnd = u.GetAncestor(window.winfo_id(), 2)
        self.previous = None
        self.event_hook = None
        self.hook_error = None
        self._remember(previous)

        def message(hwnd, msg, wp, lp, uid, ref):
            # Tk child controls need not forward WM_MOUSEACTIVATE here;
            # WM_ACTIVATE can name a same-thread window instead of the app
            # that was in front. Prefer the ordered foreground event stream.
            if msg == 0x0021:  # WM_MOUSEACTIVATE precedes a click activation.
                self._remember(u.GetForegroundWindow())
            if not self.event_hook and msg == 0x0006 and (wp & 0xffff) in (1, 2):
                self._remember(lp)
            if msg == 0x0082:
                self._remove_foreground_hook()
            result = cc.DefSubclassProc(hwnd, msg, wp, lp)
            if msg == 0x0082:  # WM_NCDESTROY
                cc.RemoveWindowSubclass(hwnd, self.proc, id(self))
                self.hwnd = None
            return result
        self.proc = self.proc_type(message)
        if not cc.SetWindowSubclass(self.hwnd, self.proc, id(self), 0):
            raise c.WinError(c.get_last_error())
        self._install_foreground_hook()

    def _install_foreground_hook(self):
        from ctypes import wintypes as W
        c, u = self.c, self.user
        self.event_type = c.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND,
                                       W.LONG, W.LONG, W.DWORD, W.DWORD)
        u.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE,
                                     self.event_type, W.DWORD, W.DWORD, W.DWORD]
        u.SetWinEventHook.restype = W.HANDLE
        u.UnhookWinEvent.argtypes = [W.HANDLE]
        u.UnhookWinEvent.restype = W.BOOL
        def foreground(hook, event, hwnd, object_id, child_id, thread, tick):
            # Out-of-context events arrive on this UI thread in order. Keep
            # only a handle/PID pair; never enter Tk from a native callback.
            if self.hwnd and self.event_hook and event == 3:
                self._remember(hwnd)
        self.foreground_proc = self.event_type(foreground)
        self.event_hook = u.SetWinEventHook(3, 3, None, self.foreground_proc, 0, 0, 0)
        if not self.event_hook:
            self.hook_error = c.get_last_error()

    def _remove_foreground_hook(self):
        if self.event_hook:
            hook, self.event_hook = self.event_hook, None
            self.user.UnhookWinEvent(hook)

    def _remember(self, hwnd):
        if not hwnd or not self.user.IsWindow(hwnd):
            return
        hwnd = self.user.GetAncestor(hwnd, 2)
        if hwnd == self.hwnd:
            return
        from ctypes import wintypes as W
        pid = W.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, self.c.byref(pid))
        self.previous = (hwnd, pid.value)

    def start_move(self):
        if not self.hwnd or not self.user.IsWindow(self.hwnd):
            return False
        self.user.ReleaseCapture()
        # Post, never Send: the native move loop must begin inside Tk's
        # event loop, without ctypes releasing the GIL around callbacks.
        return bool(self.user.PostMessageW(self.hwnd, 0x0112, 0xf012, 0))

    def restore_previous(self):
        u = self.user
        if not self.hwnd or not self.previous or u.GetForegroundWindow() != self.hwnd:
            return False
        hwnd, owner = self.previous
        if not u.IsWindow(hwnd) or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return False
        from ctypes import wintypes as W
        pid = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, self.c.byref(pid))
        return bool(pid.value == owner and u.SetForegroundWindow(hwnd))

    def detach(self):
        self._remove_foreground_hook()
        if self.hwnd:
            self.comctl.RemoveWindowSubclass(self.hwnd, self.proc, id(self))
            self.hwnd = None


class WordBook:
    def __init__(self, app, path, colors, initial_width, work_area=None):
        self.app, self.path = app, Path(path)
        self.colors, self.initial_width = colors, initial_width
        self.work_area = work_area
        self.sets = [[], [], [], []]
        self.active_set = 0
        self.visible, self.width = False, None
        self.window = None
        self._save_job = None
        self._native = None
        self._focus_job = None
        self._drag_anchor = None
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            clean = lambda words: [s for s in words if isinstance(s, str) and s] if isinstance(words, list) else []
            saved_sets = value.get('sets')
            if isinstance(saved_sets, list) and len(saved_sets) == 4:
                self.sets = [clean(words) for words in saved_sets]
                selected = value.get('active_set', 0)
                if isinstance(selected, int) and not isinstance(selected, bool) and 0 <= selected < 4:
                    self.active_set = selected
            else:
                # Migrate the old single book into set 1 without losing words.
                self.sets[0] = clean(value.get('words', []))
            self.visible = value.get('visible') is True
            width = value.get('width')
            if isinstance(width, int) and not isinstance(width, bool) and width >= 80:
                self.width = width
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @property
    def words(self):
        return self.sets[self.active_set]

    def select_set(self, index):
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < 4:
            return
        if getattr(self.app, '_pick_mode', None) == 'wordbook':
            self.app._end_pick_mode(keep_equals=True)
        self.active_set = index
        self.save()
        self.render()
        self.app.status.config(text='単語帳をセット%dに切り替えました' % (index + 1))

    def reset_current(self):
        from tkinter import messagebox
        selected = self.active_set
        if not messagebox.askyesno('現在の単語帳をリセットする',
                'セット%dに登録した単語をすべて消しますか？\n\n選択外のセットは消えません。' % (selected + 1),
                parent=self.window or self.app.root):
            return
        if selected != self.active_set:
            return
        if getattr(self.app, '_pick_mode', None) == 'wordbook':
            self.app._end_pick_mode(keep_equals=True)
        self.words.clear()
        self.save()
        self.render()
        self.app.status.config(text='単語帳のセット%dをリセットしました' % (selected + 1))

    def save(self):
        # Persist only explicitly added phrases and the window preferences.
        temporary = self.path.with_suffix('.json.tmp')
        value = dict(version=2, sets=self.sets, active_set=self.active_set, visible=self.visible, width=self.width)
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(str(temporary), str(self.path))
        except OSError as exc:
            self.app.status.config(text='単語帳を保存できませんでした：' + str(exc))

    def restore(self):
        if self.visible and not getattr(self.app, '_closing', False):
            self.open()

    def toggle(self):
        if self.window is not None:
            if self.window.state() == 'iconic':
                self.window.deiconify()
                self.window.lift()
            else:
                self.close()
        else:
            self.open()

    def open(self):
        if self.window is not None:
            self.window.lift()
            return
        bg, ink, accent = self.colors()
        previous = None
        if os.name == 'nt':
            import ctypes
            native = ctypes.WinDLL('user32')
            native.GetForegroundWindow.restype = ctypes.c_void_p
            previous = native.GetForegroundWindow()
        win = tk.Toplevel(self.app.root)
        win.withdraw()
        self.window = win
        win.title('単語帳 — セット%d' % (self.active_set + 1))
        win.configure(bg=bg)
        # No transient owner: minimizing the editor must not hide this window.
        win.attributes('-topmost', True)
        # A normal unowned toplevel, like Quick Input, is independently
        # eligible for the taskbar and Alt+Tab. A toolwindow is excluded by
        # Windows even when separately registered with the shell.
        win.resizable(True, False)
        win.minsize(80, 1)
        win.protocol('WM_DELETE_WINDOW', self.close)
        win.update_idletasks()
        if os.name == 'nt':
            self._native = _WordBookNative(win, previous)
        self.app._set_window_icons_win32(win)
        self.width = min(self.width or self.initial_width(), max(80, win.winfo_screenwidth() - 40))
        win.geometry('%dx1' % self.width)
        self.header = tk.Frame(win, bg=bg, cursor='fleur')
        self.header.pack(side='top', fill='x')
        self.header.bind('<ButtonPress-1>', self._start_drag)
        self.header.bind('<B1-Motion>', self._drag)
        self.header.bind('<ButtonRelease-1>', self._end_drag)
        self.minimize_button = tk.Button(self.header, text='－', command=self.minimize,
            bg=bg, fg=ink, relief='flat', bd=0, padx=6, pady=0,
            font=('Yu Gothic UI', 9), cursor='hand2', takefocus=True)
        self.minimize_button.pack(side='right')
        self.minimize_button.bind('<Enter>', lambda e: self.app.status.config(
            text='単語帳を最小化します（タスクバーまたは単語帳ボタンで元に戻せます）'))
        self.canvas = tk.Canvas(win, bg=bg, highlightthickness=0, width=1, height=1)
        self.scroll = tk.Scrollbar(win, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.rows = tk.Frame(self.canvas, bg=bg)
        self._rows_id = self.canvas.create_window(0, 0, window=self.rows, anchor='nw')
        self.canvas.bind('<Configure>', self._canvas_size)
        self.canvas.bind('<MouseWheel>', self._wheel)
        win.bind('<Configure>', self._resized, add=True)
        self.visible = True
        self.render()
        win.deiconify()
        win.update_idletasks()
        self._place()
        self.app.word_book_btn.config(relief='sunken', fg=accent)
        self.save()

    def _place(self):
        win, root = self.window, self.app.root
        root.update_idletasks()
        win.update_idletasks()
        border = max(0, win.winfo_rootx() - win.winfo_x())
        title = max(0, win.winfo_rooty() - win.winfo_y())
        root_border = max(0, root.winfo_rootx() - root.winfo_x())
        left, top = root.winfo_x(), root.winfo_y()
        right = left + root.winfo_width() + 2 * root_border
        bottom = root.winfo_rooty() + root.winfo_height() + root_border
        area = self.work_area((left + right) // 2, (top + bottom) // 2) if self.work_area else None
        if area is None:
            area = (0, 0, win.winfo_screenwidth(), win.winfo_screenheight())
        size = (win.winfo_width() + 2 * border, win.winfo_height() + title + border)
        gutter = self.app.editor_gutter
        gutter.redraw()
        numbers = gutter.bbox('num')
        number_left = gutter.winfo_rootx() + (numbers[0] if numbers else 0)
        x, y = word_book_position((left, top, right, bottom), size, area, number_left=number_left)
        win.geometry('+%d+%d' % (x, y))

    def _start_drag(self, event):
        self._drag_anchor = None
        if self.window is None:
            return 'break'
        if self._native is None or not self._native.start_move():
            self._drag_anchor = (event.x_root, event.y_root,
                                 self.window.winfo_x(), self.window.winfo_y())
        return 'break'

    def _drag(self, event):
        if self.window is not None and self._drag_anchor is not None:
            px, py, x, y = self._drag_anchor
            # Explicit + prefixes preserve negative virtual-screen positions.
            self.window.geometry('+%d+%d' % (x + event.x_root - px,
                                            y + event.y_root - py))
        return 'break'

    def _end_drag(self, event=None):
        self._drag_anchor = None
        return 'break'

    def minimize(self):
        self._end_drag()
        if self.window is not None:
            self.window.iconify()

    def _canvas_size(self, event):
        self.canvas.itemconfigure(self._rows_id, width=event.width)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def _resized(self, event):
        if event.widget is not self.window or event.width < 80:
            return
        if self.width == event.width:
            return
        self.width = event.width
        if self._save_job is not None:
            self.app.root.after_cancel(self._save_job)
        self._save_job = self.app.root.after(200, self._save_width)

    def _save_width(self):
        self._save_job = None
        self.save()

    def render(self):
        if self.window is None:
            return
        self.window.title('単語帳 — セット%d' % (self.active_set + 1))
        bg, ink, accent = self.colors()
        background, foreground = map(self.window.winfo_rgb, (bg, ink))
        header_bg = '#' + ''.join('%02x' % round((b * .92 + f * .08) / 257)
                                 for b, f in zip(background, foreground))
        self.header.configure(bg=header_bg)
        self.minimize_button.configure(bg=header_bg, fg=ink,
                                       activebackground=header_bg, activeforeground=ink)
        for child in self.rows.winfo_children():
            child.destroy()
        self.buttons = []
        font = self.app._editor_font()
        line_height = tkfont.Font(root=self.window, font=font).metrics('linespace')
        for index, text in enumerate(self.words):
            row = tk.Frame(self.rows, bg=bg)
            button = tk.Button(row, text=text.replace('\r', '').replace('\n', ' '),
                command=lambda value=text: self.copy(value), bg=bg, fg=ink,
                relief='flat', anchor='w', font=font, padx=8, pady=3,
                cursor='hand2', takefocus=True)
            # Windows buttons retain native padding even at pady=0. Size
            # the row from the old actual padding, keeping the text size.
            gap = max(1, round((button.winfo_reqheight() - line_height) * .25))
            row.configure(height=line_height + gap)
            row.pack(fill='x')
            row.pack_propagate(False)
            button.configure(pady=0, bd=0, highlightthickness=0)
            button.place(x=0, y=0, relwidth=1, relheight=1)
            button.bind('<Button-3>', lambda e, i=index: self.remove_menu(e, i))
            button.bind('<MouseWheel>', self._wheel)
            self.buttons.append(button)
        self.add_button = tk.Button(self.rows, text='追加', command=self.app._start_word_book_add,
            bg=bg, fg=accent, relief='flat', font=self.app._editor_font(), padx=8, pady=3,
            cursor='hand2')
        self.add_button.pack(fill='x')
        self.add_button.bind('<MouseWheel>', self._wheel)
        self.window.update_idletasks()
        header_height = self.header.winfo_reqheight()
        requested = self.rows.winfo_reqheight() + header_height
        maximum = max(100, self.window.winfo_screenheight() - 140)
        if requested > maximum:
            self.scroll.pack(side='right', fill='y')
        else:
            self.scroll.pack_forget()
        self.window.geometry('%dx%d' % (self.width, min(requested, maximum)))
        self.window.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.canvas.yview_moveto(1)

    def add(self, text):
        if not text:
            return
        self.words.append(text)
        self.save()
        self.render()

    def copy(self, text):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)
        self.app.status.config(text='単語帳の文字をコピーしました')
        if self._focus_job is not None:
            self.app.root.after_cancel(self._focus_job)
        self._focus_job = self.app.root.after_idle(self._restore_previous)

    def _restore_previous(self):
        self._focus_job = None
        if self._native is not None:
            self._native.restore_previous()

    def remove_menu(self, event, index):
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label='消す', command=lambda: self.remove(index))
        self._menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def remove(self, index):
        if 0 <= index < len(self.words):
            del self.words[index]
            self.save()
            self.render()

    def close(self):
        if getattr(self.app, '_pick_mode', None) == 'wordbook':
            self.app._end_pick_mode(keep_equals=True)
        self.visible = False
        self.shutdown()
        if self.window is not None:
            self.window.destroy()
        self.window = None
        self.app.word_book_btn.config(relief='flat', fg=self.colors()[1])

    def shutdown(self):
        # Application shutdown retains visibility for the next launch.
        self._end_drag()
        if self._focus_job is not None:
            self.app.root.after_cancel(self._focus_job)
            self._focus_job = None
        if self._native is not None:
            self._native.detach()
            self._native = None
        if self._save_job is not None:
            self.app.root.after_cancel(self._save_job)
            self._save_job = None
        self.save()
