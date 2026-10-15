# -*- coding: utf-8 -*-
"""Ctrl+G の「行へ移る・文字を探す」小さな欄（2026-10-15 うにさん）。

うにさん「Ctrl+Gで入力ボックスを出し、そこに数字を入れエンターしたら数字の行数にジャンプする。
Excelの使い勝手に近い。アプリ本体がアクティブの時にCtrl+Gをした場合のみ有効。また、数字ではなく
文字列を入れたら、同タブ内のカーソル個所から下に検索して、ヒットした文字の末尾にカーソルを置く。
最終行まで何もヒットしない場合は、1行目からカーソル位置までも見る。見つからなくても、新しい
ダイアログは出さない。入力が空欄なら何もしない。」

- 欄は本体の窓の中に置く1行の欄（別の窓にしない）。Enter で実行して閉じる。Esc・欄の外を押すと
  何もせずに閉じる。次に開くと前の入力を全部選んだ形で出す（そのまま Enter で次の該当へ）。
- 対象は Ctrl+G を押したときに焦点のあった欄（メモ欄か補正欄。ほかならメモ欄）。
- 数字（全角も・前後の空白は無視）: その行の頭へ（最終行へ移るときと同じ見せ方）。最終行より
  大きければ最終行、0 は1行目。
- 文字列: カーソルから下へ、無ければ1行目からカーソルまで。大文字と小文字は区別しない
  （検索窓の既定と同じ）。字はそのまま探す（正規表現にはしない）。見つかった字の末尾へ。
  絵文字などのまとまりの途中では止めない。見つからなければ下の欄に短く出すだけ。
- カーソルを動かすだけなので、元に戻す（Ctrl+Z）の履歴は増えない。
"""
import tkinter as tk
import unicodedata

NOT_FOUND = '「{}」は見つかりません'


def parse_line(text):
    """'12'・'１２'・' 3 ' を行の数に。数字だけでなければ None。"""
    value = unicodedata.normalize('NFKC', text).strip()
    if value and value.isdigit() and value.isascii():
        return int(value)
    return None


def find_after(text_before, text_after, needle):
    """カーソルの後ろ（text_after）から、無ければ前（text_before）から needle を探す。
    見つかった字の末尾の位置を ('after', 字数) か ('before', 字数) で返す。無ければ None。
    大文字と小文字は区別しない。"""
    if not needle:
        return None
    low = needle.lower()
    i = text_after.lower().find(low)
    if i >= 0:
        return 'after', i + len(needle)
    i = text_before.lower().find(low)
    if i >= 0:
        return 'before', i + len(needle)
    return None


class GotoBox:
    """本体の窓の中に出す Ctrl+G の欄。"""

    def __init__(self, app):
        self.app = app
        self.last = ''
        self.frame = None
        self.entry = None
        self.target = None

    # ------------------------------------------------------------- 開く・閉じる
    def open(self, event=None):
        app = self.app
        root = app.root
        try:
            focus = root.focus_get()
        except Exception:
            focus = None
        # 本体が前にあるときだけ（簡易入力・検索窓・ほかのダイアログでは効かない）
        if focus is None or focus.winfo_toplevel() is not root:
            return None
        if self.frame is not None:
            self.close()
        panes = [w for w in (getattr(app, 'editor', None), getattr(app, 'result_view', None)) if w is not None]
        target = focus if focus in panes else getattr(app, 'editor', None)
        if target is None:
            return 'break'
        self.target = target
        colors = self._colors()
        frame = tk.Frame(root, bg=colors['rule'], bd=0, highlightthickness=0)
        inner = tk.Frame(frame, bg=colors['panel'], bd=0)
        inner.pack(padx=1, pady=1)
        tk.Label(inner, text='行番号か文字列', bg=colors['panel'], fg=colors['ink'],
                 font=('Yu Gothic UI', 9)).pack(side='left', padx=(8, 4), pady=4)
        var = tk.StringVar(root, value=self.last)
        try:
            from marked_entry import MarkedEntry
            entry = MarkedEntry(inner, textvariable=var, width=24, exportselection=False,
                                font=('Yu Gothic UI', 10), relief='flat',
                                bg=colors['bg'], fg=colors['ink'], insertbackground=colors['ink'])
        except Exception:
            entry = tk.Entry(inner, textvariable=var, width=24, exportselection=False,
                             font=('Yu Gothic UI', 10), relief='flat',
                             bg=colors['bg'], fg=colors['ink'], insertbackground=colors['ink'])
        entry.pack(side='left', padx=(0, 6), pady=4, ipady=2)
        self.var, self.frame, self.entry = var, frame, entry
        entry.bind('<Return>', self._enter)
        entry.bind('<KP_Enter>', self._enter)
        entry.bind('<Escape>', lambda e: (self.close(refocus=True), 'break')[1])
        entry.bind('<FocusOut>', self._focus_out)
        frame.place(in_=target, relx=1.0, x=-10, y=8, anchor='ne')
        frame.lift()
        entry.focus_set()
        entry.select_range(0, 'end')
        entry.icursor('end')
        return 'break'

    def _colors(self):
        import app as A
        return {'bg': getattr(A, 'BG', '#ffffff'), 'panel': getattr(A, 'PANEL', '#f0f0f0'),
                'ink': getattr(A, 'INK', '#000000'), 'rule': getattr(A, 'RULE', '#888888')}

    def _focus_out(self, event=None):
        # IME の窓などで一瞬焦点が外れるだけのことがあるので、少し待って見直す
        def check():
            if self.entry is None:
                return
            try:
                focus = self.app.root.focus_get()
            except Exception:
                focus = None
            if focus is not self.entry and not str(focus or '').startswith(str(self.entry)):
                self.close()
        try:
            self.app.root.after(120, check)
        except Exception:
            self.close()

    def close(self, refocus=False):
        frame, target = self.frame, self.target
        self.frame = self.entry = None
        if frame is not None:
            try:
                frame.destroy()
            except Exception:
                pass
        if refocus and target is not None:
            try:
                target.focus_set()
            except Exception:
                pass

    # ------------------------------------------------------------------ 実行
    def _enter(self, event=None):
        text = self.var.get() if self.entry is not None else ''
        target = self.target
        self.close()
        if not text.strip() or target is None:
            if target is not None:
                target.focus_set()
            return 'break'
        self.last = text
        line = parse_line(text)
        if line is not None:
            self.goto_line(target, line)
        else:
            self.find(target, text)
        return 'break'

    def goto_line(self, widget, line):
        app = self.app
        last = int(widget.index('end-1c').split('.')[0])
        line = max(1, min(line, last))
        goto = getattr(app, '_goto_line', None)
        if callable(goto):
            goto(line, centered=True)
        else:
            widget.mark_set('insert', f'{line}.0')
            widget.see('insert')
        if widget is not getattr(app, 'editor', None):
            widget.mark_set('insert', f'{line}.0')
            widget.see('insert')
        widget.focus_set()
        return line

    def find(self, widget, needle):
        """見つかったら True。見つからなければ下の欄に知らせて False。"""
        before = widget.get('1.0', 'insert')
        after = widget.get('insert', 'end-1c')
        hit = find_after(before, after, needle)
        if hit is None:
            status = getattr(self.app, 'status', None)
            if status is not None:
                try:
                    shown = needle if len(needle) <= 20 else needle[:20] + '…'
                    status.config(text=NOT_FOUND.format(shown))
                except Exception:
                    pass
            widget.focus_set()
            return False
        side, offset = hit
        mark = 'correctnote_goto_hit'
        # 字数は Python の数え方。Tk 8.6.9 の +Nc は1字ずつ前へ進むので、印と相対の移動だけを使う
        # （返ってきた index を渡し直さない）
        widget.mark_set(mark, ('insert' if side == 'after' else '1.0') + f'+{offset}c')
        try:
            from text_edit import cluster_edge
            cluster_edge(lambda *a: widget.tk.call(widget._w, *a), mark, 'forward')
        except Exception:
            pass
        widget.tag_remove('sel', '1.0', 'end')
        widget.mark_set('insert', mark)
        widget.mark_unset(mark)
        widget.see('insert')
        widget.focus_set()
        return True


def install(app):
    """本体の窓に Ctrl+G を張る（本体の窓の中の部品にだけ届く）。"""
    box = GotoBox(app)
    app._goto_box = box
    for seq in ('<Control-g>', '<Control-G>'):
        app.root.bind(seq, box.open, add='+')
    return box
