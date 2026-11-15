# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""「ひらがなのまま通す語」の窓（2026-11-14 うにさん「特定の単語だけひらがなのままにするリストが要る。…オプションで別
ウインドウを出し、個別に自由につけ足しや無効にできるようにする。既に入れたひらがなのまま通すルールもそこへ入れる。ルールが
品詞によるものはオンオフできるように。きれいは個別に置き、ユーザーがそれを消したらきれいは漢字となる」）。

上の段「決まり」: 品詞・語の種類による決まりを1行ずつ、チェックでオン／オフ（説明を添える）。
下の段「語」: かなの語の一覧。行ごとに有効／無効のチェックと削除。入力欄と「足す」で付け足す。初めから入っている語にも
同じ操作ができる。「初めの状態に戻す」は確かめてから。
読み書きは kana_keep_list の関数だけ（ファイルは触らない）。操作のたびに保存し、閉じた時か「適用」を押した時に、中身が
変わっていれば app.kana_keep_changed() を呼ぶ（開いているタブを解析し直す）。位置は設定の kana_keep_window_pos に覚える。
"""
import tkinter as tk
from tkinter import messagebox

import kana_keep_list
import ui_lang

POS_KEY = 'kana_keep_window_pos'


def _t(ja, en):
    return ja if ui_lang.is_japanese() else en


class KanaKeepWindow:
    def __init__(self, app):
        self.app = app
        self.win = None
        self.rule_vars = {}
        self.word_vars = {}
        self.start_version = None

    # --- open / close -------------------------------------------------
    def open(self):
        if self.win is not None:
            try:
                self.win.deiconify()
                self.win.lift()
                self.win.focus_force()
                return self.win
            except tk.TclError:
                self.win = None
        kana_keep_list.load()
        self.start_version = kana_keep_list.version()
        colors = _colors(self.app)
        win = self.win = tk.Toplevel(self.app.root)
        win.title(_t('ひらがなのまま通す語', 'Keep in kana'))
        win.configure(bg=colors['bg'])
        try:
            win.transient(self.app.root)
        except tk.TclError:
            pass
        win.withdraw()          # 中身を作って高さを決めてから出す（開いた瞬間に大きさが変わって見えない）
        win.protocol('WM_DELETE_WINDOW', self.close)
        win.bind('<Escape>', lambda e: self.close())
        self._build(win, colors)
        self._place(win, self._fit_height(win))
        win.deiconify()
        _dark_titlebar(win, colors['bg'])
        win.lift()
        try:
            win.focus_force()
        except tk.TclError:
            pass
        return win

    WIDTH = 520
    MIN_LIST = 90           # 縮めても残す一覧の高さ（2〜3行）
    SCREEN_MARGIN = 80      # 画面の下（タスクバー）に残す分

    def _fit_height(self, win):
        """開いた時の高さ: 語の一覧が全部入る高さ。画面に収まらなければ画面の作業領域まで（一覧はスクロール）。少ない時は
        その分だけ縮める。手で縮めても下のボタンは見切れない（ボタンの行を先に下へ詰めてある・最小の高さ）
        （2026-11-15 うにさん「下のボタンが見切れている。デフォルトで縦に伸ばすが、手動で縮めた時もボタンを見切れさせない。
        項目が少ない時は縦を縮める」）。"""
        try:
            win.update_idletasks()
            rest = win.winfo_reqheight() - self.canvas.winfo_reqheight()     # 一覧の外（説明・決まり・入力・ボタン）
            words = self.words_frame.winfo_reqheight() + 4
            limit = max(rest + self.MIN_LIST, win.winfo_screenheight() - self.SCREEN_MARGIN)
            height = max(rest + self.MIN_LIST, min(rest + words, limit))
            win.minsize(360, rest + self.MIN_LIST)
            return int(height)
        except tk.TclError:
            return 560

    def _place(self, win, height=560):
        pos = None
        try:
            pos = self.app.settings.get(POS_KEY)
        except Exception:
            pos = None
        size = '%dx%d' % (self.WIDTH, height)
        if isinstance(pos, str) and pos.startswith('+'):
            try:
                x, y = (int(v) for v in pos[1:].split('+')[:2])
                # 覚えた位置のままだと下が画面の外へ出るなら、上へ寄せる
                y = max(0, min(y, win.winfo_screenheight() - self.SCREEN_MARGIN - height))
                win.geometry('%s+%d+%d' % (size, x, y))
            except (ValueError, tk.TclError):
                win.geometry(size + pos)
        else:
            try:
                self.app._place_dialog(win, self.WIDTH, height)
            except Exception:
                win.geometry(size)

    def _remember_place(self):
        try:
            self.app.settings.set(POS_KEY, '+%d+%d' % (self.win.winfo_x(), self.win.winfo_y()))
            self.app.settings.save()
        except Exception:
            pass

    def apply(self):
        """中身が変わっていれば、開いているタブを解析し直す。"""
        now = kana_keep_list.version()
        if now != self.start_version:
            self.start_version = now
            changed = getattr(self.app, 'kana_keep_changed', None)
            if changed is not None:
                changed()
            return True
        return False

    def close(self):
        if self.win is None:
            return
        self._remember_place()
        self.apply()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.win = None

    # --- the contents ----------------------------------------------------
    def _build(self, win, c):
        font = ('Yu Gothic UI', 10)
        small = ('Yu Gothic UI', 8)
        tk.Label(win, text=_t('決まり', 'Rules'), bg=c['bg'], fg=c['ink'], font=('Yu Gothic UI', 10, 'bold'),
                 anchor='w').pack(fill='x', padx=16, pady=(14, 2))
        tk.Label(win, text=_t('品詞・語の種類で、ひらがなのまま通す決まりです。チェックを外すと、その決まりは使いません。',
                              'Rules by part of speech or word type. Uncheck a rule to stop using it.'),
                 bg=c['bg'], fg=c['muted'], font=small, anchor='w', justify='left',
                 wraplength=480).pack(fill='x', padx=16)
        self.rules_frame = tk.Frame(win, bg=c['bg'])
        self.rules_frame.pack(fill='x', padx=16, pady=(4, 8))
        tk.Label(win, text=_t('語', 'Words'), bg=c['bg'], fg=c['ink'], font=('Yu Gothic UI', 10, 'bold'),
                 anchor='w').pack(fill='x', padx=16, pady=(6, 2))
        tk.Label(win, text=_t('ここにある語は、どの段でも漢字にしません。語の一覧は決まりより強く、決まりのオン・オフに'
                              '関係なく、有効な語はかなのまま通します。チェックを外すと無効（漢字になります）、'
                              '「削除」で一覧から外します。',
                              'Words here are never turned into kanji. The word list is stronger than the rules: an '
                              'enabled word stays in kana whatever the rules say. Uncheck to disable (the word becomes '
                              'kanji); "Delete" removes it from the list.'),
                 bg=c['bg'], fg=c['muted'], font=small, anchor='w', justify='left',
                 wraplength=480).pack(fill='x', padx=16)
        add = tk.Frame(win, bg=c['bg'])
        add.pack(fill='x', padx=16, pady=(6, 4))
        self.entry = tk.Entry(add, font=font, bg=c['panel'], fg=c['ink'], insertbackground=c['ink'], relief='flat',
                              highlightthickness=1, highlightbackground=c['rule'], highlightcolor=c['accent'],
                              selectbackground=c['accent'], selectforeground=c['panel'])
        self.entry.pack(side='left', fill='x', expand=True)
        self.entry.bind('<Return>', lambda e: self.add())
        self.add_button = tk.Button(add, text=_t('足す', 'Add'), command=self.add, **_button(c))
        self.add_button.pack(side='left', padx=(6, 0))
        # 下のボタンの行を先に下へ詰める（窓を縮めても見切れず、一覧のほうがスクロールになる）
        bottom = tk.Frame(win, bg=c['bg'])
        bottom.pack(side='bottom', fill='x', padx=16, pady=(4, 14))
        wrap = tk.Frame(win, bg=c['rule'])
        wrap.pack(fill='both', expand=True, padx=16, pady=(2, 6))
        self.canvas = tk.Canvas(wrap, bg=c['panel'], highlightthickness=0, height=1)
        bar = tk.Scrollbar(wrap, orient='vertical', command=self.canvas.yview, bg=c['panel'], troughcolor=c['bg'],
                           activebackground=c['rule'], highlightthickness=0, bd=0)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True, padx=1, pady=1)
        self.words_frame = tk.Frame(self.canvas, bg=c['panel'])
        self.canvas.create_window((0, 0), window=self.words_frame, anchor='nw')
        self.words_frame.bind('<Configure>',
                              lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.reset_button = tk.Button(bottom, text=_t('初めの状態に戻す', 'Restore defaults'), command=self.reset,
                                      **_button(c))
        self.reset_button.pack(side='left')
        tk.Button(bottom, text=_t('閉じる', 'Close'), command=self.close, **_button(c, strong=True)).pack(side='right')
        self.apply_button = tk.Button(bottom, text=_t('適用', 'Apply'), command=self.apply, **_button(c))
        self.apply_button.pack(side='right', padx=(0, 6))
        self._colors = c
        self.refresh()

    def refresh(self):
        # 作り直す行は今の配色で（開いたあとでテーマを替えていても）
        c = self._colors = _colors(self.app)
        for frame in (self.rules_frame, self.words_frame):
            for child in frame.winfo_children():
                child.destroy()
        self.rule_vars, self.word_vars, self.target_labels = {}, {}, {}
        english = not ui_lang.is_japanese()
        for rule in kana_keep_list.rules():
            rid = rule['id']
            box = tk.Frame(self.rules_frame, bg=c['bg'])
            box.pack(fill='x', pady=(0, 2))
            head = tk.Frame(box, bg=c['bg'])
            head.pack(fill='x')
            var = self.rule_vars[rid] = tk.BooleanVar(value=rule['on'])
            tk.Checkbutton(head, text=rule['label_en'] if english else rule['label'], variable=var, anchor='w',
                           bg=c['bg'], fg=c['ink'], activebackground=c['bg'], activeforeground=c['ink'],
                           selectcolor=c['panel'], highlightthickness=0,
                           font=('Yu Gothic UI', 10),
                           command=lambda rid=rid, var=var: self.set_rule(rid, var.get())).pack(side='left')
            targets = tk.Label(box, text=self._targets_text(rule['targets'], rule.get('members')), bg=c['bg'], fg=c['ink'],
                               font=('Yu Gothic UI', 8), anchor='w', justify='left', wraplength=440)
            self.target_labels[rid] = targets
            tk.Button(head, text=_t('対象の語', 'Words'),
                      command=lambda rid=rid: self.toggle_targets(rid), **_button(c)).pack(side='right')
            tk.Label(box, text=rule['description_en'] if english else rule['description'], bg=c['bg'], fg=c['muted'],
                     font=('Yu Gothic UI', 8), anchor='w', justify='left', wraplength=450).pack(fill='x', padx=(22, 0))
        items = [(e['word'], e['enabled'], e['default']) for e in kana_keep_list.entries()]
        if not items:
            tk.Label(self.words_frame, text=_t('（語はありません）', '(no words)'), bg=c['panel'],
                     fg=c['muted']).pack(anchor='w', padx=8, pady=6)
        for word, on, default in items:
            row = tk.Frame(self.words_frame, bg=c['panel'])
            row.pack(fill='x', padx=6, pady=1)
            var = self.word_vars[word] = tk.BooleanVar(value=on)
            tk.Checkbutton(row, text=ui_lang.raw(word) if hasattr(ui_lang, 'raw') else word, variable=var,
                           bg=c['panel'], fg=c['ink'], activebackground=c['panel'], activeforeground=c['ink'],
                           selectcolor=c['bg'], highlightthickness=0,
                           font=('Yu Gothic UI', 10), anchor='w',
                           command=lambda w=word, var=var: self.set_word(w, var.get())).pack(side='left')
            # 同梱の語の印（初めから）は出さない（2026-11-15 うにさん「（初めから）の表示は要らない」）。区別は default に残す
            tk.Button(row, text=_t('削除', 'Delete'), command=lambda w=word: self.remove(w), **_button(c)).pack(side='right')

    @staticmethod
    def _targets_text(targets, members=()):
        parts = []
        if targets:
            parts.append(_t('対象の語（見るだけ）: ', 'Words (view only): ') + '・'.join(targets))
        if members:
            parts.append(_t('含む物: ', 'Includes: ') + '・'.join(members))
        if not parts:
            return _t('品詞・語の種類で決めるので、対象の語の一覧はありません。',
                      'Decided by part of speech or word type: no word list.')
        return '\n'.join(parts)

    def toggle_targets(self, rule_id):
        """決まりの対象の語を開く・畳む（見せるだけ。v1 では編集しない）。開いていれば True。"""
        label = self.target_labels.get(rule_id)
        if label is None:
            return False
        if label.winfo_manager():
            label.pack_forget()
            return False
        label.pack(fill='x', padx=(22, 0))
        return True

    # --- the operations (each one goes through kana_keep_list) -----------
    def set_rule(self, rule_id, on):
        kana_keep_list.set_rule(rule_id, bool(on))

    def set_word(self, word, on):
        kana_keep_list.set_word(word, bool(on))

    def add(self, word=None):
        word = (word if word is not None else self.entry.get()).strip()
        if not word:
            return False
        kana_keep_list.add_word(word)
        try:
            self.entry.delete(0, 'end')
        except tk.TclError:
            pass
        self.refresh()
        return True

    def remove(self, word):
        kana_keep_list.remove_word(word)
        self.refresh()

    def reset(self, ask=None):
        ask = ask or (lambda: messagebox.askyesno(
            _t('初めの状態に戻す', 'Restore defaults'),
            _t('足した語・無効にした語・決まりのオン／オフを、すべて初めの状態に戻します。よろしいですか？',
               'All added words, disabled words and rule settings go back to the defaults. Continue?'),
            parent=self.win))
        if not ask():
            return False
        kana_keep_list.reset()
        self.refresh()
        return True


def _dark_titlebar(win, bg):
    """暗い配色の時は、窓の枠（タイトルバー）も暗くする（本体の窓と同じ Windows の属性・Windows 以外は何もしない）。"""
    import sys
    if sys.platform != 'win32':
        return
    try:
        r, g, b = (v / 65535.0 for v in win.winfo_rgb(bg))
        dark = 0.299 * r + 0.587 * g + 0.114 * b < 0.5
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def _button(c, strong=False):
    """補正の判断の窓と同じボタンの塗り（閉じるは濃い地・ほかは欄の地）。"""
    if strong:
        return dict(bg=c['ink'], fg=c['bg'], activebackground=c['accent'], activeforeground=c['panel'], relief='flat', bd=0,
                    font=('Yu Gothic UI', 9), padx=14, pady=3, cursor='hand2', highlightthickness=0)
    return dict(bg=c['panel'], fg=c['ink'], activebackground=c['rule'], activeforeground=c['ink'], relief='flat', bd=1,
                font=('Yu Gothic UI', 9), padx=10, pady=3, cursor='hand2', highlightthickness=0)


def _colors(app):
    """窓の色は本体の配色の名前（BG・PANEL・INK・MUTED・RULE・ACCENT）から取る。テーマを替えると、本体が開いている窓の
    部品の色を古い配色から新しい配色へ置き換える（app._restyle_widget）ので、補正の判断の窓と同じく塗り直される
    （2026-11-15 うにさん「ひらがなのまま通すウィンドウは、ダークモードに対応してください」）。"""
    import sys
    app_module = sys.modules.get(type(app).__module__) or __import__('app')
    return dict(accent=getattr(app_module, 'ACCENT', '#2c5f6f'),
                bg=getattr(app_module, 'BG', '#f6f4ee'), ink=getattr(app_module, 'INK', '#1c2b2d'),
                muted=getattr(app_module, 'MUTED', '#8a8577'), panel=getattr(app_module, 'PANEL', '#f0f0ed'),
                rule=getattr(app_module, 'RULE', '#d8d3c4'))


def open_from_app(app):
    window = getattr(app, '_kana_keep_window', None)
    if window is None:
        window = app._kana_keep_window = KanaKeepWindow(app)
    return window.open()
