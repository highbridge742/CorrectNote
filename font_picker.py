# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""フォントの一覧（お気に入りのピンつき・2026-10-30 うにさん）。

    「フォントにお気に入りを付けます。ピンのアイコンを、各フォントの左側に表示してクリックでオンオフ。オンにした
    フォントは、一覧の上部へ優先的に並べられる。…ピン付を上に置き、ルーラーで区切ってその下は今ある通常のリスト
    で、通常のリストの中にもピンをオンにした項目は残しておく。」

前のプルダウン（ttk.Combobox）は行ごとの印を押せないので、Canvas に行を描く一覧に替えた。上にピンを付けた
フォント、線で区切って、下に全部のフォント（ピンを付けたものも残す）。名前を押すと選ぶ、ピンを押すとオンオフ。
上の入力欄に打つと、その字を含むフォントだけに絞る（大文字小文字は区別しない）。
"""
import tkinter as tk

ROW_PAD = 4
PIN_W = 26
RULE_H = 9


# 日本語の名前で並ぶことのあるフォントの英語の名前（2026-10-31 うにさん「最初から入っている Yu Mincho が、
# リスト内にないんだけどなんで？」: Windows の一覧では 游明朝 の名で並ぶ）。Tk に英語の名前を渡すと、その PC の
# 一覧の名前に読み替えるので、ここに無い名前も一覧から外れはしない（英語の名前の添え書きが出ないだけ）
ENGLISH_NAMES = (
    'Yu Mincho', 'Yu Mincho Demibold', 'Yu Mincho Light', 'Yu Gothic', 'Yu Gothic Light', 'Yu Gothic Medium',
    'MS Mincho', 'MS PMincho', 'MS Gothic', 'MS PGothic', 'Meiryo', 'BIZ UDGothic', 'BIZ UDPGothic',
    'BIZ UDMincho Medium', 'BIZ UDPMincho Medium', 'UD Digi Kyokasho N-R', 'UD Digi Kyokasho NK-R',
    'UD Digi Kyokasho NP-R', 'UD Digi Kyokasho N-B', 'HGMinchoB', 'HGPMinchoB', 'HGSMinchoB', 'HGMinchoE',
    'HGPMinchoE', 'HGSMinchoE', 'HGGothicE', 'HGPGothicE', 'HGSGothicE', 'HGGothicM', 'HGPGothicM',
    'HGSGothicM', 'HGMaruGothicMPRO', 'HGKyokashotai', 'HGPKyokashotai', 'HGSKyokashotai', 'HGGyoshotai',
    'HGPGyoshotai', 'HGSGyoshotai', 'HGSeikaishotaiPRO', 'HGSoeiKakugothicUB', 'HGPSoeiKakugothicUB',
    'HGSSoeiKakugothicUB', 'HGSoeiKakupoptai', 'HGPSoeiKakupoptai', 'HGSSoeiKakupoptai',
    'HGSoeiPresenceEB', 'HGPSoeiPresenceEB', 'HGSSoeiPresenceEB', 'HGGothicE')


def english_aliases(root, families):
    """{一覧の名前: 英語の名前}。英語の名前を Tk がこの PC の一覧の名前に読み替えたものだけ。"""
    import tkinter.font as tkfont
    present = set(families)
    out = {}
    for name in ENGLISH_NAMES:
        try:
            actual = tkfont.Font(root=root, family=name).actual().get('family')
        except tk.TclError:
            continue
        if actual in present and actual.casefold() != name.casefold():
            out.setdefault(actual, name)
    return out


# 本文の字の初期設定が入っていない PC での代わり（2026-10-31 うにさん「Noto Serifがない場合、メイリオ、その次に
# 游明朝、その次にWindowsの判断」）。英語・日本語どちらの名前でも Tk は同じ字に読み替える
DEFAULT_FALLBACKS = ('Noto Serif', 'メイリオ', '游明朝')


def installed(root, family):
    """この PC にそのフォントが在るか。無い名前は Tk が別の字に読み替えるので、在り得ない名前の読み替え先と比べる。"""
    import tkinter.font as tkfont
    try:
        if family in tkfont.families(root):
            return True
        actual = tkfont.Font(root=root, family=family).actual().get('family')
        stand_in = tkfont.Font(root=root, family='CorrectNote no such font').actual().get('family')
    except tk.TclError:
        return False
    return bool(actual) and actual != stand_in


def default_family(root, chain=DEFAULT_FALLBACKS):
    """並びのうち最初に在るフォント。どれも無ければ並びの最初（Windows が代わりの字を選ぶ）。"""
    for family in chain:
        if installed(root, family):
            return family
    return chain[0]


def listed_name(root, family, families):
    """設定のフォント名（英語の名前のこともある）を、一覧の名前にする。一覧に無ければそのまま。"""
    if family in families:
        return family
    import tkinter.font as tkfont
    try:
        actual = tkfont.Font(root=root, family=family).actual().get('family')
    except tk.TclError:
        return family
    return actual if actual in families else family


class FontList(tk.Frame):
    def __init__(self, master, families, favorites, selected, on_select, on_favorites,
                 bg='#ffffff', fg='#000000', muted='#888888', accent='#3366cc', select_bg='#dde8f6',
                 font=('Yu Gothic UI', 10), height=220, aliases=None):
        super().__init__(master, bg=bg)
        self.families = list(families)
        # 一覧の名前 → 英語の名前（Windows は日本語のフォントを日本語の名前で並べる: 游明朝＝Yu Mincho）
        self.aliases = dict(aliases or {})
        self.favorites = [f for f in favorites if f in set(self.families)]
        self.selected = selected
        self.on_select, self.on_favorites = on_select, on_favorites
        self.colors = dict(bg=bg, fg=fg, muted=muted, accent=accent, select_bg=select_bg)
        self.font = font
        self.filter = ''
        self.rows = []          # (y0, y1, family, section)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, height=height)
        self.bar = tk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Configure>', self._configured)
        self._shown = False
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.canvas.bind(sequence, self._wheel)
        try:
            linespace = int(self.tk.call('font', 'metrics', font, '-linespace'))
        except tk.TclError:
            linespace = 18
        self.row_h = linespace + ROW_PAD * 2
        self.canvas.configure(yscrollincrement=self.row_h)

    def _configured(self, event=None):
        self.render()
        if not self._shown and self.canvas.winfo_height() > 1:
            self._shown = True           # 開いたとき、いま使っているフォントの行が見えるように
            self.see(self.selected)

    # --- 並び ----------------------------------------------------------------
    def _matches(self, family):
        return (not self.filter or self.filter in family.casefold()
                or self.filter in self.aliases.get(family, '').casefold())

    def sections(self):
        """(上のピンの行, 下の全部の行)。上も一覧の順（2026-10-31 うにさん「並びは元のリスト順にする」）。"""
        favorites = set(self.favorites)
        pinned = [f for f in self.families if f in favorites and self._matches(f)]
        rest = [f for f in self.families if self._matches(f)]
        return pinned, rest

    def set_filter(self, text):
        self.filter = (text or '').strip().casefold()
        self.render()
        self.canvas.yview_moveto(0)

    def select(self, family):
        self.selected = family
        self.render()

    # --- 描く ----------------------------------------------------------------
    def _pin(self, x, y, on):
        """押しピン（つまみ・胴・つば・針）。オンは塗り、オフは薄い輪郭だけ。"""
        c = self.canvas
        color = self.colors['accent'] if on else self.colors['muted']
        fill = color if on else self.colors['bg']
        cx = x + 10
        c.create_rectangle(cx - 4, y - 8, cx + 4, y - 6, outline=color, fill=fill, tags=('pin',))       # つまみ
        c.create_polygon(cx - 3, y - 6, cx + 3, y - 6, cx + 4, y, cx - 4, y,
                         outline=color, fill=fill, tags=('pin',))                                        # 胴
        c.create_line(cx - 6, y + 1, cx + 7, y + 1, fill=color, width=2, tags=('pin',))                 # つば
        c.create_line(cx, y + 1, cx, y + 8, fill=color, width=1, tags=('pin',))                         # 針

    def render(self):
        c = self.canvas
        c.delete('all')
        self.rows = []
        width = max(c.winfo_width(), 200)
        y = 0
        pinned, rest = self.sections()
        favorites = set(self.favorites)

        def row(family, section):
            nonlocal y
            y0, y1 = y, y + self.row_h
            if family == self.selected:
                c.create_rectangle(0, y0, width, y1, outline='', fill=self.colors['select_bg'])
            self._pin(4, (y0 + y1) // 2, family in favorites)
            # 名前は一覧の表記のまま（游明朝。英語の名前は添えない・2026-10-31 うにさん「游明朝という表記のままでよい」）。
            # 英語の名前（aliases）は、上の欄に打って絞るときにだけ使う
            c.create_text(PIN_W + 4, (y0 + y1) // 2, text=family, anchor='w', font=self.font, fill=self.colors['fg'])
            self.rows.append((y0, y1, family, section))
            y = y1
        for family in pinned:
            row(family, 'pinned')
        if pinned:
            mid = y + RULE_H // 2
            c.create_line(4, mid, width - 4, mid, fill=self.colors['muted'])
            y += RULE_H
        for family in rest:
            row(family, 'all')
        c.configure(scrollregion=(0, 0, width, max(y, 1)))

    def see(self, family):
        """選んでいるフォントの行が見えるように。ピンを付けたフォントは上のピンの段の行（2026-10-31 うにさん
        「ピン付きのフォントで決定して、フォントウインドウを開きなおしたら、上のピンのグループのほうをフォーカス
        した状態にする」）、ほかは下の全部の一覧の行。"""
        sections = [r[3] for r in self.rows if r[2] == family]
        want = 'pinned' if 'pinned' in sections else 'all'
        for y0, y1, name, section in self.rows:
            if name == family and section == want:
                total = max(1, int(float(self.canvas.cget('scrollregion').split()[3])))
                height = max(1, self.canvas.winfo_height())
                top = self.canvas.canvasy(0)
                if y0 < top or y1 > top + height:
                    self.canvas.yview_moveto(max(0, y0 - height / 3) / total)
                return

    # --- 押す ----------------------------------------------------------------
    def _row_at(self, event):
        y = self.canvas.canvasy(event.y)
        for y0, y1, family, section in self.rows:
            if y0 <= y < y1:
                return family
        return None

    def _click(self, event):
        family = self._row_at(event)
        if family is None:
            return 'break'
        if event.x < PIN_W:
            self.toggle(family)
        else:
            self.selected = family
            self.render()
            self.on_select(family)
        return 'break'

    def toggle(self, family):
        top = self.canvas.yview()[0]
        if family in self.favorites:
            self.favorites.remove(family)
        else:
            self.favorites.append(family)
        self.on_favorites(list(self.favorites))
        self.render()
        self.canvas.yview_moveto(top)

    def _wheel(self, event):
        if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0:
            step = -3
        else:
            step = 3
        self.canvas.yview_scroll(step, 'units')
        return 'break'
