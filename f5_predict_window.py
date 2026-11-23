# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""F5 の予測の行頭・文末の候補を編集する窓（2026-11-20 うにさん「オプションに行頭の候補をカスタム、文末の候補をカスタムを
追加し、別ウインドウで候補を編集可能とします。並べ替えもできる」）。

全角あり・半角だけの2組を切り替えて、候補の追加・変更・削除・上下の並べ替え・既定に戻す。変えるたびに設定
（f5_predict_lists）へ保存する。並べた順がそのまま候補の順（既定の「打つ手間の多い順」は使わない）。
"""
import tkinter as tk

import f5_predict


def _lists(app):
    got = app.settings.get('f5_predict_lists') or {}
    return {k: list(v) for k, v in got.items()} if isinstance(got, dict) else {}


def current(app, name):
    return f5_predict.custom_list(app, name) or f5_predict.default_list(name)


def store(app, name, items):
    """name の並びを保存する。既定と同じなら設定から外す（既定の並びが変わった時に追いつけるように）。"""
    lists = _lists(app)
    items = [x for x in items if x]
    if items == f5_predict.default_list(name) or not items:
        lists.pop(name, None)
    else:
        lists[name] = items
    app.settings.set('f5_predict_lists', lists)
    try:
        app.settings.save()
    except Exception:
        pass


# 印（2026-11-20 16:10Z うにさん「␣を全角スペース、この半分幅を半角スペース、タブスペースは[Tab]と書いてください」）。
# 半角空白の印は ␣ と同じ形で幅の狭い ˽（U+02FD・Yu Gothic UI 12pt で ␣ が 16px・˽ が 6px）
MARKS = {'\u3000': '␣', ' ': '˽', '\t': '[Tab]'}


def f5_predict_window_spaces(environ=None):
    import os
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_WINDOW_SPACES') != '0'


# 印を付けるのは、後ろに字が無い空白だけ（2026-11-20 16:44Z うにさん「変換候補のスペース3種は、後ろに文字があるときは
# 各記号を出さずただの空白表現にする。後ろに文字がないところだけ、␣などを書く」）。後ろに字がある空白はそのまま見せる
# （タブは一覧で字の形にならないので半角空白4つで見せる）。CN_F5_MARK_TRAILING_ONLY=0 で前の形（全部の空白に印）
# 後ろに字がある空白の見せ方の幅（2026-11-21 うにさん「タブスペースは全角と幅の表示が変わらない。今1として、1.5個分に
# する。半角は幅が短い。全角スペースの半分の横幅にする」）。全角空白の幅を1として、タブ＝1.5（全角空白＋EN SPACE U+2002）、
# 半角空白＝0.5（EN SPACE）。Yu Gothic UI 12pt で 全角空白 16px・タブ 24px・半角 8px（10pt で 13・20・7px）。
# 字の大きさに比べた幅なので、どの大きさでも同じ比。CN_F5_PLAIN_WIDTH=0 で前の形（タブ＝半角空白4つ・半角はそのまま）
PLAIN_OLD = {'\t': '    '}
PLAIN = {'\t': '\u3000\u2002', ' ': '\u2002'}


def plain_table(environ=None):
    import os
    environ = os.environ if environ is None else environ
    return PLAIN_OLD if environ.get('CN_F5_PLAIN_WIDTH') == '0' else PLAIN


def mark_trailing_only(environ=None):
    import os
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_MARK_TRAILING_ONLY') != '0'


def marked(text):
    """一覧・候補の窓に出す形（後ろに字の無いスペース・タブを印に）。保存と挿入は本物の字のまま。"""
    text = text or ''
    if not mark_trailing_only():
        return ''.join(MARKS.get(c, c) for c in text)
    body = text.rstrip(''.join(MARKS))
    tail = text[len(body):]
    plain = plain_table()
    return ''.join(plain.get(c, c) for c in body) + ''.join(MARKS.get(c, c) for c in tail)


UNDO_LIMIT = 100


def window_undo_on(environ=None):
    import os
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_WINDOW_UNDO') != '0'


def english_ui(environ=None):
    """アプリが英語で動いているか（CN_PREDICT_WINDOW_EN=0 で見ない＝前の形）。"""
    import os
    environ = os.environ if environ is None else environ
    if environ.get('CN_PREDICT_WINDOW_EN') == '0':
        return False
    try:
        import ui_lang
        return not ui_lang.is_japanese()
    except Exception:
        return False


def open_window(app, kind='head', colors=None):
    """kind: 'head'（行頭）か 'end'（文末）。"""
    # 本体のテーマの色（ダークモードでも白いままにしない・2026-11-20 15:30Z うにさん「ダークモードに対応し」）
    colors = dict(colors or {})
    bg = colors.get('bg', '#f6f4ee')
    ink = colors.get('ink', '#1c2b2d')
    panel = colors.get('panel', '#ffffff')
    sel = colors.get('sel', '#cfe0f5')
    muted = colors.get('muted', ink)
    button = dict(bg=panel, fg=ink, activebackground=sel, activeforeground=ink, relief='flat',
                  highlightthickness=1, highlightbackground=muted)
    old = getattr(app, '_f5_predict_window', None)
    if old is not None:
        try:
            old.destroy()
        except tk.TclError:
            pass
    dlg = tk.Toplevel(app.root)
    app._f5_predict_window = dlg
    dlg.title('F5 予測の行頭の候補' if kind == 'head' else 'F5 予測の文末の候補')
    dlg.configure(bg=bg)
    place = getattr(app, '_place_dialog', None)
    if place is not None:
        try:
            place(dlg, 460, 420)
        except Exception:
            pass
    names = [n for n in f5_predict.LIST_NAMES if n.startswith(kind)]
    english = english_ui()
    # 英語で動いている時は半角時の一覧を開き、全角時のボタンは日本語向けと書く（2026-11-23 うにさん。日本語では今のまま）
    which = tk.StringVar(master=dlg, value=next((n for n in names if n.endswith('_narrow')), names[0]) if english else names[0])
    top = tk.Frame(dlg, bg=bg)
    top.pack(fill='x', padx=10, pady=(10, 4))
    for n in names:
        label = f5_predict.list_label(n) + ('（日本語向け）' if english and n.endswith('_wide') else '')
        tk.Radiobutton(top, text=label, variable=which, value=n, bg=bg, fg=ink,
                       selectcolor=panel, activebackground=bg, activeforeground=ink,
                       command=lambda: refresh()).pack(side='left', padx=(0, 10))
    mid = tk.Frame(dlg, bg=bg)
    mid.pack(fill='both', expand=True, padx=10, pady=4)
    lb = tk.Listbox(mid, font=('Yu Gothic UI', 12), height=10, exportselection=False, activestyle='none',
                    bg=panel, fg=ink, selectbackground=sel, selectforeground=ink, highlightthickness=1,
                    highlightbackground=muted, relief='flat')
    lb.pack(side='left', fill='both', expand=True)
    try:      # 候補の一覧の絵文字を色付きで（emoji_widgets・2026-11-21 うにさん）
        import emoji_widgets
        emoji_widgets.listbox(lb)
    except Exception:
        pass
    buttons = tk.Frame(mid, bg=bg)
    buttons.pack(side='left', fill='y', padx=(8, 0))
    entry_row = tk.Frame(dlg, bg=bg)
    entry_row.pack(fill='x', padx=10, pady=(4, 10))
    tk.Label(entry_row, text='候補の字:', bg=bg, fg=ink).pack(side='left')
    entry = tk.Entry(entry_row, font=('Yu Gothic UI', 12), width=16, bg=panel, fg=ink, insertbackground=ink,
                     selectbackground=sel, selectforeground=ink, relief='flat', highlightthickness=1,
                     highlightbackground=muted)
    entry.pack(side='left', padx=(6, 0))

    # 2026-11-20 15:42Z うにさん「候補を追加したら、候補入力欄を追加した文字を入れておく。選択して、候補入力欄を空欄にして
    # 変更を押したら、削除する。スペースだけの候補も作成できるようにする。末尾に入れたスペースも保存する。タブキーでタブを
    # 入れられるようにする」: 字は削らずにそのまま（空だけは足さない）。一覧ではスペース・タブを印で見せる（印は表示だけ・
    # 保存と挿入は本物の字）。CN_F5_WINDOW_SPACES=0 で前の形（前後の空白を削る・追加で欄を空にする・印なし）
    spaces = f5_predict_window_spaces()
    shown = []          # 一覧に出している本物の字（印にする前）

    def text_of_entry():
        text = entry.get()
        return text if spaces else text.strip()

    def items():
        return list(shown)

    def selected():
        sel = lb.curselection()
        return sel[0] if sel else None

    # 戻す（この窓の中の Undo・2026-11-21 01:55Z うにさん「カスタムのボタンに、戻すを追加」）: 追加・変更・削除・上へ・下へ・
    # ドラッグの並べ替え（1回のドラッグで1つ）の前の並びを積む。CN_F5_WINDOW_UNDO=0 でボタンを出さない
    history = []

    def remember():
        history.append((which.get(), items()))
        del history[:-UNDO_LIMIT]

    def put(values, at=None, record=True):
        if record:
            remember()
        store(app, which.get(), values)
        refresh(at)

    def undo(_e=None):
        if not history:
            return 'break'
        name, values = history.pop()
        if which.get() != name:
            which.set(name)
        store(app, name, values)
        refresh()
        return 'break'

    def refresh(at=None):
        lb.delete(0, 'end')
        shown[:] = current(app, which.get())
        for c in shown:
            lb.insert('end', marked(c) if spaces else c)
        if at is not None and lb.size():
            at = max(0, min(at, lb.size() - 1))
            lb.selection_set(at)
            lb.see(at)

    def add():
        text = text_of_entry()
        if not text:
            return
        values = items()
        if text in values:
            return
        at = selected()
        at = len(values) if at is None else at + 1
        values.insert(at, text)
        if not spaces:
            entry.delete(0, 'end')
        put(values, at)             # 欄には足した字を残す

    def change():
        at, text = selected(), text_of_entry()
        if at is None:
            return
        if not text:
            if spaces:
                delete()            # 欄を空にして変更 → その行を消す
            return
        values = items()
        if text in values and values.index(text) != at:
            return
        values[at] = text
        put(values, at)

    def delete():
        at = selected()
        if at is None:
            return
        values = items()
        del values[at]
        put(values, at)

    def move(step):
        at = selected()
        if at is None:
            return
        to = at + step
        values = items()
        if not 0 <= to < len(values):
            return
        values[at], values[to] = values[to], values[at]
        put(values, to)

    def reset():
        store(app, which.get(), f5_predict.default_list(which.get()))
        refresh()

    def chosen(_e=None):
        at = selected()
        if at is not None and at < len(shown):
            entry.delete(0, 'end')
            entry.insert(0, shown[at])

    # ドラッグで並べ替え
    drag = {}

    def press(e):
        drag['from'] = lb.nearest(e.y)
        drag['recorded'] = False

    def motion(e):
        frm = drag.get('from')
        if frm is None:
            return
        to = lb.nearest(e.y)
        if to != frm and 0 <= to < lb.size():
            values = items()
            values.insert(to, values.pop(frm))
            drag['from'] = to
            put(values, to, record=not drag.get('recorded'))
            drag['recorded'] = True

    def release(_e):
        drag.pop('from', None)
    lb.bind('<<ListboxSelect>>', chosen)
    lb.bind('<ButtonPress-1>', press, add=True)
    lb.bind('<B1-Motion>', motion)
    lb.bind('<ButtonRelease-1>', release, add=True)

    def enter(_e=None):
        # 一覧で選んで「候補の字」を変えて Enter → その行を変更（変更ボタンと同じ・空なら削除）。選んでいなければ追加
        # （2026-11-20 15:30Z・15:42Z うにさん）
        at = selected()
        text = text_of_entry()
        if at is not None and (text != shown[at] if at < len(shown) else True) and (text or spaces):
            change()
        else:
            add()
        return 'break'
    entry.bind('<Return>', enter)

    def tab(_e=None):
        if not spaces:
            return None
        entry.insert('insert', '\t')           # Tab はタブの字（焦点を移さない）
        return 'break'
    entry.bind('<Tab>', tab)
    dlg.bind('<Escape>', lambda e: dlg.destroy())          # Esc で閉じる
    # 「既定に戻す」は外した（2026-11-20 15:30Z うにさん「規定に戻すを削除」）。並びは利用者のもの
    rows = [('追加', add), ('変更', change), ('削除', delete), ('上へ', lambda: move(-1)), ('下へ', lambda: move(1))]
    if window_undo_on():
        rows.append(('戻す', undo))
        dlg.bind('<Control-z>', undo)
        dlg.bind('<Control-Z>', undo)
    rows.append(('閉じる', dlg.destroy))
    for text, fn in rows:
        tk.Button(buttons, text=text, width=10, command=fn, **button).pack(fill='x', pady=2)
    dlg._f5 = dict(listbox=lb, entry=entry, which=which, add=add, change=change, delete=delete, move=move,
                   reset=reset, refresh=refresh, enter=enter, tab=tab, shown=shown, undo=undo, history=history)
    refresh()
    return dlg
