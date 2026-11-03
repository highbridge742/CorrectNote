# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""選択してF3で検索（2026-10-31 うにさん）。

何も選んでいない F3 は今までどおり Enter（app._on_f3_return）。字を選んで F3 を押したら、既定の
ブラウザで、選んだ字の Google 検索を開く。オプション「選択してF3で検索」（既定オン・f3_search）と、
その前に確かめる「選択してF3で検索する前に確認する」（既定オン・f3_search_confirm）。

確かめの枠: 「選択した文字列で検索しますか？」「F3またはエンターで実行」。F3 か Enter で開き、
枠の外をクリックするか Esc で取りやめる（候補一覧と同じく、枠から焦点が外れたら閉じる）。
"""
import urllib.parse

SEARCH_URL = 'https://www.google.com/search?q='
TOP_URL = 'https://www.google.com/'
QUERY_LIMIT = 1000          # 長すぎる選択は頭だけ（URL が長くなりすぎない）
QUESTION = '選択した文字列で検索しますか？'
HINT = 'F3またはエンターで実行'


def selected_text(widget):
    """欄で選んでいる字（改行・前後の空白はならす）。選んでいなければ ''。"""
    try:
        if not widget.tag_ranges('sel'):
            return ''
        text = widget.get('sel.first', 'sel.last')
    except Exception:
        return ''
    return ' '.join(str(text).split())[:QUERY_LIMIT]


def search_url(text):
    return SEARCH_URL + urllib.parse.quote_plus(text)


def open_top(opener=None):
    """既定のブラウザで Google の検索の入口を開く。開けたら True。"""
    if opener is None:
        import webbrowser
        opener = webbrowser.open
    try:
        return bool(opener(TOP_URL))
    except Exception:
        return False


def open_search(text, opener=None):
    """既定のブラウザで検索を開く。開けたら True。"""
    if opener is None:
        import webbrowser
        opener = webbrowser.open
    try:
        return bool(opener(search_url(text)))
    except Exception:
        return False


def _no_activate(top):
    """枠を押しても CorrectNote の窓から焦点を移さない（Windows: WS_EX_NOACTIVATE）。"""
    import sys
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        user = ctypes.windll.user32
        top.update_idletasks()
        hwnd = user.GetParent(top.winfo_id()) or top.winfo_id()
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x00000080
        user.SetWindowLongW(hwnd, GWL_EXSTYLE, user.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        pass


class Confirm:
    """確かめの枠（枠の無い小窓）。F3・Enter で run、Esc・枠の外のクリック・ほかのアプリへ移ると取りやめ。

    枠は焦点を取らない（取らせると、焦点の移り変わりで開いた途端に閉じることがあった・2026-10-31 うにさん
    「実装されてないように見えます」）。キーは元の欄で受ける（欄の先頭に TAG を差し込み、閉じたら外す）。"""
    TAG = 'CnF3SearchConfirm'
    WATCH_MS = 300

    def __init__(self, widget, run, colors=None, font=None):
        import tkinter as tk
        self.widget, self.run, self.done = widget, run, False
        self._tag = self._press = None
        bg, fg, rule = colors or ('#f0f0ed', '#1c2b2d', '#8a9396')
        top = self.top = tk.Toplevel(widget)
        top.withdraw()
        top.wm_overrideredirect(True)
        top.configure(bg=rule)
        body = self.body = tk.Frame(top, bg=bg, padx=14, pady=10, highlightthickness=0)
        body.pack(padx=1, pady=1)
        options = dict(bg=bg, fg=fg, anchor='w', justify='left')
        if font is not None:
            options['font'] = font
        tk.Label(body, text=QUESTION, **options).pack(anchor='w')
        tk.Label(body, text=HINT, **options).pack(anchor='w', pady=(4, 0))
        top.update_idletasks()
        x, y = self._place(top.winfo_reqwidth(), top.winfo_reqheight())
        top.geometry('+%d+%d' % (x, y))
        _no_activate(top)
        top.deiconify()
        try:
            top.lift()
        except Exception:
            pass
        self._listen()
        try:
            import no_activate
            watch = not no_activate.other_app_in_front()    # 開いたときに前にいたなら、離れたら閉じる
        except Exception:
            watch = False
        if watch:
            self._watch()

    def _listen(self):
        w = self.widget
        try:
            for sequence in ('<F3>', '<Return>', '<KP_Enter>'):
                w.bind_class(self.TAG, sequence, self._accept)
            w.bind_class(self.TAG, '<Escape>', self._cancel)
            w.bind_class(self.TAG, '<ButtonPress>', self._cancel)
            w.bind_class(self.TAG, '<Key>', lambda event: 'break')     # ほかのキーは本文へ流さない
            w.bindtags((self.TAG,) + tuple(t for t in w.bindtags() if t != self.TAG))
            self._tag = self.TAG
        except Exception:
            self._tag = None
        # アプリの中のどこを押しても（枠の中を除く）取りやめ。'all' の束縛に足し、閉じたら元に戻す
        # （ボタンごとの束縛が 'all' に在ると、Tk はそちらだけを走らせるので、在るものにも足す）
        try:
            command = w.register(self._pressed)
            saved = []
            for sequence in ('<ButtonPress>', '<ButtonPress-1>', '<ButtonPress-2>', '<ButtonPress-3>'):
                previous = w.tk.call('bind', 'all', sequence)
                if sequence != '<ButtonPress>' and not previous:
                    continue
                saved.append((sequence, previous))
                w.tk.call('bind', 'all', sequence, '+%s %%W' % command)
            self._press = (command, saved)
        except Exception:
            self._press = None

    def _pressed(self, path):
        if not str(path).startswith(str(self.top)):
            self._cancel()

    def _watch(self):
        """ほかのアプリが前に出たら取りやめる。"""
        if self.done:
            return
        try:
            import no_activate
            if no_activate.other_app_in_front():
                self._cancel()
                return
        except Exception:
            pass
        try:
            self.top.after(self.WATCH_MS, self._watch)
        except Exception:
            pass

    def _place(self, width, height):
        """選んだ字の下（入らなければ上）。欄の中に収める。"""
        w = self.widget
        left, top = w.winfo_rootx(), w.winfo_rooty()
        right, bottom = left + w.winfo_width(), top + w.winfo_height()
        box = None
        try:
            box = w.bbox('sel.first')
        except Exception:
            box = None
        if box:
            x, y = left + box[0], top + box[1] + box[3] + 6
            if y + height > bottom:
                y = top + box[1] - height - 6
        else:
            x, y = left + (w.winfo_width() - width) // 2, top + (w.winfo_height() - height) // 2
        x = max(left, min(x, right - width))
        y = max(top, min(y, bottom - height))
        return x, y

    def _close(self):
        if self.done:
            return False
        self.done = True
        if self._tag is not None:
            try:
                self.widget.bindtags(tuple(t for t in self.widget.bindtags() if t != self._tag))
            except Exception:
                pass
        if self._press is not None:
            command, saved = self._press
            try:
                for sequence, previous in saved:
                    self.widget.tk.call('bind', 'all', sequence, previous)
                self.widget.deletecommand(command)
            except Exception:
                pass
        try:
            self.top.destroy()
        except Exception:
            pass
        try:
            self.widget.focus_set()
        except Exception:
            pass
        return True

    def _accept(self, event=None):
        if self._close():
            self.run()
        return 'break'

    def _cancel(self, event=None):
        self._close()
        return 'break'


def handle(app, widget):
    """F3 を検索として受けたら True（呼ぶ側は 'break' を返す）。選んでいない・オフなら False（Enter のまま）。"""
    settings = getattr(app, 'settings', None)
    if settings is None or not settings.get('f3_search'):
        return False
    open_now = getattr(app, '_f3_confirm', None)
    if open_now is not None and not open_now.done:
        open_now._accept()          # 確かめの枠が出ている間の F3 は「実行」
        return True
    return handle_text(app, widget, selected_text(widget))


def handle_text(app, widget, text):
    """text を検索する（オプションどおり確かめてから）。始めたら True。text が空・オフなら False。
    再変換の候補一覧で項目を選んでいないときの F3 もここ（選んでいる語・2026-11-01 うにさん）。"""
    settings = getattr(app, 'settings', None)
    text = ' '.join(str(text or '').split())[:QUERY_LIMIT]
    if settings is None or not settings.get('f3_search') or not text:
        return False

    def run():
        if open_search(text):
            try:
                app.status.config(text='ブラウザで検索しました: ' + (text if len(text) <= 30 else text[:30] + '…'))
            except Exception:
                pass

    if settings.get('f3_search_confirm'):
        colors = None
        try:
            # 色は動いているアプリの模組から読む。`import app` はしない（`python app.py` で起動すると模組は
            # __main__ なので、app.py をもう一度まるごと読み込んでしまう・2026-10-31 実機で効かなかった）
            import sys
            owner = sys.modules.get(type(app).__module__)
            colors = (owner.PANEL, owner.INK, owner.RULE)
        except Exception:
            pass
        try:
            font = app._quick_font() if hasattr(app, '_quick_font') else None
        except Exception:
            font = None
        app._f3_confirm = Confirm(widget, run, colors, font)
    else:
        run()
    return True
