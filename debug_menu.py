# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""デバッグメニュー（2026-10-18 うにさん）。補正が始まるまでの待ちと、タブの
ホイールの量・跳ね返り防止の待ちを、その場で縮めて試す窓。

待ちだけを変える。補正の答えは変えない。値は settings.json の
'debug_timings' に、既定と違うものだけを入れる（個人の語彙などには触らない）。

既定は、いまのコードの値（各モジュールの定数・CorrectNoteApp の定数）。
ここに数字を写さない（決めているのは最初の行）。モジュールの定数は、
保存に値があるときだけ書き換え、書き換える前の値を控えて戻す
（試験が定数を patch していても、保存が空なら触らない）。
スライダーの最大は既定、ただし持ち主に `<名前>_MAX` があればそれ（タブの
ホイール・2026-10-18 うにさん）。最小は処理が成り立つ最小値で、その理由を
項目ごとに書く。
"""
import importlib
import tkinter as tk

_ZERO_STOPS = ('見に行く繰り返し。0 だと Tk の手が空かなくなり（空回り）、'
               '打鍵の描画と入力が止まる。1ms が下限')
_ZERO_WAITS = '0 でも答えが届くまでは出さない（出すのは答えを待つ）。0 は答えが来しだい出す'
_ZERO_ONCE = '1回きりの予約で繰り返さない。0 でも止まらない（Tk の次の回で走る）'
_ZERO_GUARD = '0 は跳ね返りの防止を切るだけで、処理は止まらない'

# (鍵, 名前, 持ち主, 名前, 単位, 最小, 最小の理由)
#   持ち主 'app' は CorrectNoteApp の定数（その窓のインスタンスへ当てる）。
#   それ以外はモジュール名（モジュールの定数へ当てる。読む側は呼ぶたびに引く）。
ITEMS = (
    ('ime_quiet', 'IME の確定から、補正を出すまでの待ち',
     'analysis_input', 'DISPLAY_QUIET_IME_MS', 'ms', 0, _ZERO_WAITS),
    ('key_quiet', '1字打ってから、補正を出すまでの待ち',
     'analysis_input', 'DISPLAY_QUIET_MS', 'ms', 0,
     _ZERO_WAITS + '（統合表示の自動反映では、打っている途中の語に入ることがある）'),
    ('busy_gap', '入力中に他の行の補正結果を認識する間隔',
     'app', 'ANALYZE_BUSY_GAP_MS', 'ms', 1, _ZERO_STOPS),
    ('poll', '補正結果を反映する間隔（入力中は無効）',
     'app', 'ANALYZE_POLL_MS', 'ms', 1, _ZERO_STOPS),
    ('busy_window', '最後の操作から、入力中とみなす長さ',
     'app', 'ANALYZE_BUSY_WINDOW_MS', 'ms', 0,
     '0 は「入力中とみなさない」だけで、処理は止まらない'),
    ('paint_gap', '見えている行の補正を、途中で出す間隔',
     'app', 'ANALYZE_PAINT_GAP_MS', 'ms', 0,
     '0 は行が片付くたびに出す（描き直しが増えるだけで、止まらない）'),
    ('follow_gap', '打った行を出したあと、周りの行を出す間隔',
     'app', 'ANALYZE_TYPED_FOLLOW_GAP_MS', 'ms', 0,
     '0 は行が片付くたびに出す（描き直しが増えるだけで、止まらない）'),
    ('ime_poll_active', 'IME の変換中を見張る間隔',
     'app', '_IME_POLL_ACTIVE_MS', 'ms', 1, _ZERO_STOPS),
    ('ime_poll_idle', 'IME の変換が始まったかを見張る間隔',
     'app', '_IME_POLL_IDLE_MS', 'ms', 1, _ZERO_STOPS),
    ('bg_gap', '裏のタブの補正を始めるまで',
     'app', 'ANALYZE_BG_GAP_MS', 'ms', 0,
     _ZERO_ONCE + '。そのあとの繰り返しには別の下限（25ms）がある'),
    ('quick_quiet', '簡易入力：打ってから、補正を出すまでの待ち',
     'quick_analysis', 'DISPLAY_QUIET_MS', 'ms', 0, _ZERO_WAITS),
    ('tab_wheel_step', 'タブを切り替えるホイールの量（1目盛り＝120）',
     'app', 'TAB_WHEEL_STEP', '', 1,
     '0 だと量を貯めずに毎回切り替わり、1 と同じになる（量0の知らせは先に捨てる）。1 が下限'),
    ('tab_wheel_same', 'タブを切り替えたあと、同じ向きを受け付けるまで',
     'app', 'TAB_WHEEL_SAME_MS', 'ms', 0, _ZERO_GUARD),
    ('tab_wheel_reverse', 'タブを切り替えたあと、逆向きを無視する間',
     'app', 'TAB_WHEEL_REVERSE_MS', 'ms', 0, _ZERO_GUARD),
    # 「右ボタンを離したあと、逆向きを無視する間」（tab_wheel_release）は外した
    # （2026-10-19 うにさん。離したあとも上の「逆向き」で抑える）。保存に残った鍵は
    # normalize が読み飛ばす。
)
KEYS = tuple(item[0] for item in ITEMS)
# 窓の見出し（その鍵の項目の前に出す・2026-10-18 うにさん）。2つ目からは前に1行あける。
# 打鍵から計算を始めるまで・下準備と打った行を見に行く間隔（1ms／5ms）の4項目は、
# うにさんの指定で窓から外した（コードの値はそのまま）。
SECTIONS = (('ime_quiet', '【解析】'), ('tab_wheel_step', '【タブ移動】'))
_BY_KEY = {item[0]: item for item in ITEMS}
_ORIGINAL = {}   # 書き換えたモジュールの定数の、書き換える前の値


def _owner(owner, app=None):
    if owner == 'app':
        if app is not None:
            return type(app)
        import sys
        # exe では app.py が __main__ として動く。もう一度 import しない。
        for name in ('app', '__main__'):
            module = sys.modules.get(name)
            if module is not None and hasattr(module, 'CorrectNoteApp'):
                return module.CorrectNoteApp
        return importlib.import_module('app').CorrectNoteApp
    return importlib.import_module(owner)


def default(key, app=None):
    """コードに書いてある値（窓の値は、クラスの定数を見る）。"""
    _, _, owner, name, _, _, _ = _BY_KEY[key]
    if key in _ORIGINAL:
        return _ORIGINAL[key]
    return int(getattr(_owner(owner, app), name))


def minimum(key):
    return _BY_KEY[key][5]


def maximum(key, app=None):
    """スライダーの上限。持ち主に `<名前>_MAX` があればそれ、無ければ既定。"""
    _, _, owner, name, _, _, _ = _BY_KEY[key]
    high = getattr(_owner(owner, app), name + '_MAX', None)
    return default(key, app) if high is None else int(high)


def clamp(key, value, app=None):
    return max(minimum(key), min(maximum(key, app), int(value)))


def parse(key, text, app=None):
    """入力欄の文字を値にする。数でなければ None（受け付けない）、範囲の外は丸める。"""
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    return clamp(key, value, app)


def normalize(saved, app=None):
    """保存された値のうち、知っている鍵で、整数で、範囲の中のものだけ残す。
    既定と同じ値は残さない（既定に戻したのと同じ）。"""
    out = {}
    if not isinstance(saved, dict):
        return out
    for key, value in saved.items():
        if key not in _BY_KEY or type(value) is not int:
            continue
        try:
            low, high = minimum(key), maximum(key, app)
            usual = default(key, app)
        except Exception:
            continue
        if low <= value <= high and value != usual:
            out[key] = value
    return out


def values(app):
    saved = normalize(app.settings.get('debug_timings'), app)
    return {key: saved.get(key, default(key, app)) for key in KEYS}


def apply(app, saved=None):
    """全部の項目を当てる（保存に無いものは既定へ戻す）。"""
    saved = normalize(app.settings.get('debug_timings') if saved is None else saved, app)
    for key in KEYS:
        _, _, owner, name, _, _, _ = _BY_KEY[key]
        if owner == 'app':
            if key in saved:
                setattr(app, name, saved[key])
            else:
                app.__dict__.pop(name, None)
            continue
        module = _owner(owner)
        if key in saved:
            _ORIGINAL.setdefault(key, int(getattr(module, name)))
            setattr(module, name, saved[key])
        elif key in _ORIGINAL:
            setattr(module, name, _ORIGINAL.pop(key))


def set_value(app, key, value, save=True):
    """1項目を変えて、すぐ当てる。既定と同じなら保存から外す。"""
    value = clamp(key, value, app)
    saved = normalize(app.settings.get('debug_timings'), app)
    if value == default(key, app):
        saved.pop(key, None)
    else:
        saved[key] = value
    # DEFAULTS の {} を共有しないよう、いつも新しい辞書を入れる
    app.settings.set('debug_timings', dict(saved))
    apply(app, saved)
    if save:
        app.settings.save()
    return value


def open_window(app, colors=None):
    """項目ごとに 名前・数値の欄・スライダー・「デフォルトに戻す」を並べた窓。"""
    colors = dict(colors or {})
    bg = colors.get('bg', '#f6f4ee')
    ink = colors.get('ink', '#1c2b2d')
    muted = colors.get('muted', '#8a8577')
    panel = colors.get('panel', bg)
    old = getattr(app, '_debug_window', None)
    if old is not None:
        try:
            if old.winfo_exists():
                old.deiconify()
                old.lift()
                old.focus_set()
                return old
        except tk.TclError:
            pass
    dlg = tk.Toplevel(app.root)
    app._debug_window = dlg
    dlg.title('デバッグメニュー')
    dlg.configure(bg=bg)
    try:
        dlg.transient(app.root)
    except tk.TclError:
        pass
    place = getattr(app, '_place_dialog', None)
    if place is not None:
        place(dlg, 640, 620)
    tk.Label(dlg, text='補正が始まるまでの待ち（とタブのホイール）を、その場で縮めて試せます。'
             '最大はおおむね今の既定です。補正の答えは変わりません。',
             bg=bg, fg=ink, justify='left', wraplength=600,
             font=('Yu Gothic UI', 9)).pack(anchor='w', padx=12, pady=(10, 6))
    outer = tk.Frame(dlg, bg=bg)
    outer.pack(fill='both', expand=True, padx=(12, 0), pady=(0, 6))
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
    bar = tk.Scrollbar(outer, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    body = tk.Frame(canvas, bg=bg)
    canvas.create_window((0, 0), window=body, anchor='nw')
    body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

    def wheel(event):
        try:
            canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        except tk.TclError:
            pass
        return 'break'
    dlg.bind('<MouseWheel>', wheel)
    current = values(app)
    rows = {}
    pending = [None]

    def save_now():
        pending[0] = None
        app.settings.save()

    def save_soon():
        # スライダーを引いている間に何度も書かない（当てるのは、すぐ）
        if pending[0] is not None:
            try:
                dlg.after_cancel(pending[0])
            except tk.TclError:
                pass
        pending[0] = dlg.after(400, save_now)
    headings = dict(SECTIONS)
    row = 0
    for key, label, _owner_name, _name, unit, low, reason in ITEMS:
        if key in headings:
            tk.Label(body, text=headings[key], bg=bg, fg=ink,
                     font=('Yu Gothic UI', 11, 'bold')).grid(
                         row=row, column=0, sticky='w', pady=((0 if row == 0 else 18), 6))
            row += 1
        high = maximum(key, app)
        usual = default(key, app)
        frame = tk.Frame(body, bg=bg)
        frame.grid(row=row, column=0, sticky='ew', pady=(0, 8))
        row += 1
        span = '%d〜%d%s（既定 %d%s）' % (low, high, unit, usual, unit)
        tk.Label(frame, text=label, bg=bg, fg=ink,
                 font=('Yu Gothic UI', 10, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w')
        text = tk.StringVar(master=dlg, value=str(current[key]))
        number = tk.IntVar(master=dlg, value=current[key])
        fixed = low >= high
        entry = tk.Entry(frame, textvariable=text, width=7, bg=panel, fg=ink,
                         justify='right', relief='flat', highlightthickness=1)
        entry.grid(row=1, column=0, sticky='w', padx=(0, 6))
        scale = tk.Scale(frame, from_=low, to=high if not fixed else low + 1, orient='horizontal',
                         variable=number, showvalue=False, length=300, resolution=1,
                         bg=bg, fg=ink, highlightthickness=0, troughcolor=panel)
        scale.grid(row=1, column=1, sticky='w')
        button = tk.Button(frame, text='デフォルトに戻す')
        button.grid(row=1, column=2, sticky='w', padx=(8, 0))
        tk.Label(frame, text=span, bg=bg, fg=muted,
                 font=('Yu Gothic UI', 8)).grid(row=1, column=3, sticky='w', padx=(8, 0))
        tk.Label(frame, text='最小の理由：' + reason, bg=bg, fg=muted, justify='left',
                 wraplength=600, font=('Yu Gothic UI', 8)).grid(
                     row=2, column=0, columnspan=4, sticky='w')
        if fixed:
            entry.configure(state='disabled')
            scale.configure(state='disabled')
        rows[key] = dict(text=text, number=number, entry=entry, scale=scale, button=button)

        def commit(value, key=key, text=text, number=number):
            value = set_value(app, key, value, save=False)
            save_soon()
            text.set(str(value))
            if number.get() != value:
                number.set(value)
            return value

        # commit は既定の引数で縛る（ループの最後の行のものを呼ばないように）
        def from_scale(raw, commit=commit):
            try:
                commit(int(float(raw)))
            except (TypeError, ValueError, tk.TclError):
                pass

        def from_entry(event=None, key=key, text=text, commit=commit):
            value = parse(key, text.get(), app)
            if value is None:
                # 数でなければ受け付けない（いまの値へ戻す）
                text.set(str(values(app)[key]))
                return 'break'
            commit(value)
            return 'break'

        def reset(key=key, commit=commit):
            commit(default(key, app))
        scale.configure(command=from_scale)
        entry.bind('<Return>', from_entry)
        entry.bind('<FocusOut>', from_entry)
        button.configure(command=reset)
        rows[key]['reset'] = reset
        rows[key]['from_entry'] = from_entry

    def reset_all():
        for key in KEYS:
            rows[key]['reset']()
    foot = tk.Frame(dlg, bg=bg)
    foot.pack(fill='x', padx=12, pady=(0, 10))
    tk.Button(foot, text='すべてデフォルトに戻す', command=reset_all).pack(side='left')
    tk.Button(foot, text='閉じる', command=dlg.destroy).pack(side='right')

    def forget(event=None):
        if event is None or event.widget is dlg:
            if pending[0] is not None:
                try:
                    dlg.after_cancel(pending[0])
                except tk.TclError:
                    pass
                save_now()
            if getattr(app, '_debug_window', None) is dlg:
                app._debug_window = None
    dlg.bind('<Destroy>', forget, add='+')
    dlg._debug_rows = rows
    dlg._debug_reset_all = reset_all
    return dlg
