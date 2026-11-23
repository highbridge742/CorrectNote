# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""縮小表示（俯瞰の速い形・overview_fast）の中の絵文字も色付きで（2026-11-21 うにさん「絵文字を白黒で見せないようにする」・
10:34Z「縮小の間だけ、見える範囲の絵文字の上に、縮小の字の大きさに合わせた色付きの絵を重ねる」）。

縮小表示は本文の欄の分身（Tk の peer）で、emoji_color の色付け（EmojiOverlay）は掛けられない（分身は tkinter の部品では
なく、タグは本文の欄と共有なので、本文の欄の色付けの隠しタグは本文の欄の見えている所にしか付いていない）。
・縮小に入った時と、縮小の中で動かして MOVE_QUIET_MS 止まった時に（動かしている間は絵を外す: 動かすたびに置き直すと
  1回 約25ms かかり、掴んで動かす動きが重くなる）、分身の見えている範囲の絵文字を探し、
  その字の枠（bbox）の大きさで色付きの絵を描いて、枠の上に重ねる（地は字の地の色・選んだ範囲などのタグの地も見る）
・絵文字が無ければ何もしない（見えている字を1回読むだけ）
・縮小から出る時に外す。CN_OVERVIEW_EMOJI=0 で前の形（白黒）
・重ねるのは、縮小の中でも元の字の大きさのままの行（タイトル・目次＝cn_head_* のタグ、ブックマーク＝cn_ov_bookmark）の
  絵文字だけ（11:43Z うにさん「タイトル目次ブックマーク以外の、小さくなっているところであれば色がなくてよい。処理が軽く
  なるならそうする」）。小さく描く本文の行は白黒のまま、字も読まない（その行の範囲だけを読む）。
  CN_OVERVIEW_EMOJI_HEAD_ONLY=0 で見えている全部の行（前の形）
"""
import os

MAX_LABELS = 300
MOVE_QUIET_MS = 100
WATCH_MS = 150      # 縮小の間、字の並びが後から動いていないか（最初と最後の絵文字の枠だけ見る）


HEAD_PREFIXES = ('cn_head',)
BOOKMARK_TAG = 'cn_ov_bookmark'


def head_only(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_EMOJI_HEAD_ONLY') != '0'


def on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_EMOJI') != '0'


class PeerEmoji:
    def __init__(self, pane, name):
        self.pane = pane
        self.name = name
        self.tk = pane.tk
        self.labels = []
        self.shown = []
        self.images = {}
        self.job = None
        self.watch_job = None
        self.marks = ()         # 置いた時の（最初と最後の絵文字の位置, その枠）

    def _call(self, *args):
        return self.tk.call(self.name, *args)

    def soon(self):
        if self.job is not None:
            return
        try:
            self.job = self.pane.after_idle(self._run)
        except Exception:
            self.job = None

    def moving(self):
        """動かした: 絵を外し、止まってから置き直す。"""
        self.clear()            # 予約も取り消す（止まってから MOVE_QUIET_MS 後に1回）
        try:
            self.job = self.pane.after(MOVE_QUIET_MS, self._run)
        except Exception:
            self.job = None

    def _run(self):
        self.job = None
        try:
            self.refresh()
        except Exception:
            pass

    def _bg(self, index, base):
        try:
            tags = self.tk.splitlist(self._call('tag', 'names', index))
        except Exception:
            return base
        bg = base
        for tag in tags:
            tag = str(tag)
            if tag.startswith('cn_paper_') or tag.startswith('cn_emoji_hide'):
                continue
            try:
                value = str(self._call('tag', 'cget', tag, '-background'))
            except Exception:
                value = ''
            if value:
                bg = value
        return bg

    def _hex(self, color):
        r, g, b = self.pane.winfo_rgb(color)
        return '#%02x%02x%02x' % (r >> 8, g >> 8, b >> 8)

    def placements(self):
        from emoji_color import EMOJI, emoji_spans, emoji_columns, _units
        call = self._call
        try:
            if not int(self.tk.call('winfo', 'ismapped', self.name)):
                return []
            width = int(self.tk.call('winfo', 'width', self.name))
            height = int(self.tk.call('winfo', 'height', self.name))
        except Exception:
            return []
        first, last = '@0,0', '@%d,%d' % (width, height)
        pieces = self.pieces(first, last)
        if not pieces:
            return []
        width_of = len if emoji_columns(self.pane) == 1 else _units
        base_bg = str(call('cget', '-background'))
        out = []
        for line0, lead_from, text in pieces:
          lead = width_of(str(call('get', '%d.0' % line0, lead_from))) if lead_from else 0
          for offset, line in enumerate(text.split('\n')):
            row = line0 + offset
            base = lead if offset == 0 else 0
            for start, end in emoji_spans(line):
                c0 = base + width_of(line[:start])
                a = self.tk.splitlist(call('bbox', '%d.%d' % (row, c0)))
                if len(a) != 4:
                    continue
                x, y, w, h = (int(v) for v in a)
                c = self.tk.splitlist(call('bbox', '%d.%d' % (row, base + width_of(line[:end]))))
                if len(c) == 4 and int(c[1]) < y + h and int(c[1]) + int(c[3]) > y and int(c[0]) > x:
                    w = int(c[0]) - x               # 字の並び（肌の色など）の終わりまで
                if w < 2 or h < 2:
                    continue
                out.append((x, y, w, h, line[start:end], self._hex(self._bg('%d.%d' % (row, c0), base_bg)),
                            '%d.%d' % (row, c0)))
                if len(out) >= MAX_LABELS:
                    return out
        return out

    def _head_rows(self, first, last):
        """見えている範囲の、元の字の大きさの行（タイトル・目次・ブックマーク）の行番号。"""
        call = self._call
        top = int(str(call('index', first)).split('.')[0])
        bottom = int(str(call('index', last)).split('.')[0])
        rows = set()
        tags = [str(t) for t in self.tk.splitlist(call('tag', 'names'))
                if str(t) == BOOKMARK_TAG or str(t).startswith(HEAD_PREFIXES)]
        for tag in tags:
            got = self.tk.splitlist(call('tag', 'prevrange', tag, '%d.0' % top))
            spans = [got] if len(got) == 2 else []
            at = '%d.0' % top
            while True:
                got = self.tk.splitlist(call('tag', 'nextrange', tag, at, '%d.0 lineend' % bottom))
                if len(got) != 2:
                    break
                spans.append(got)
                at = str(got[1])
            for a, b in spans:
                ra, rb = int(str(a).split('.')[0]), int(str(b).split('.')[0])
                if str(b).endswith('.0') and rb > ra:
                    rb -= 1                         # 'r.0' から 'r+1.0'（行まるごと）
                rows.update(range(max(ra, top), min(rb, bottom) + 1))
        return top, sorted(rows)

    def pieces(self, first, last):
        """[(1行目の行番号, 1行目の字の頭の位置か None, 字)]: 絵文字を探す字。絵文字が無ければ []。"""
        from emoji_color import EMOJI
        call = self._call
        if not head_only():
            text = str(call('get', first, last)) + str(call('get', last))
            if not EMOJI.search(text):
                return []
            return [(int(str(call('index', first)).split('.')[0]), first, text)]
        top, rows = self._head_rows(first, last)
        out = []
        i = 0
        while i < len(rows):
            j = i
            while j + 1 < len(rows) and rows[j + 1] == rows[j] + 1:
                j += 1
            start = first if rows[i] == top else '%d.0' % rows[i]
            text = str(call('get', start, '%d.0 lineend' % rows[j]))
            if EMOJI.search(text):
                out.append((rows[i], start if rows[i] == top else None, text))
            i = j + 1
        return out

    def _image(self, text, width, height, bg):
        key = (text, width, height, bg)
        img = self.images.get(key)
        if img is None:
            from emoji_color import renderer
            r = renderer()
            if r is None:
                return None
            if len(self.images) > 400:
                self.images.clear()
            import tkinter as tk
            px = max(4, round(min(width + 2, height) * 0.85))
            img = self.images[key] = tk.PhotoImage(master=self.pane, data=r.render(text, px, width, height, bg))
        return img

    def refresh(self):
        if not on():
            return self.clear()
        found = self.placements()
        if found == self.shown:
            return
        import tkinter as tk
        for i, (x, y, w, h, text, bg, _index) in enumerate(found):
            if i < len(self.labels):
                label = self.labels[i]
            else:
                label = tk.Label(self.pane.master, bd=0, highlightthickness=0, padx=0, pady=0, takefocus=0)
                self.labels.append(label)
            if i < len(self.shown) and self.shown[i] == found[i]:
                continue
            img = self._image(text, w, h, bg)
            if img is None:
                continue
            label.configure(image=img, bg=bg)
            self.tk.call('place', label._w, '-in', self.name, '-x', x, '-y', y, '-width', w, '-height', h,
                         '-bordermode', 'outside')
            self.tk.call('raise', label._w, self.name)
        for label in self.labels[len(found):]:
            label.place_forget()
        self.shown = found
        self._watch_start()

    def _sig(self):
        out = []
        for item in (self.shown[:1] + self.shown[-1:]) if self.shown else ():
            try:
                out.append(tuple(int(v) for v in self.tk.splitlist(self._call('bbox', item[6]))))
            except Exception:
                out.append(None)
        return tuple(out)

    def _watch_start(self):
        """字の並びが後から動いた（縮小に入った後の組み直しなど）時に置き直す。動いていなければ枠を2つ測るだけ。"""
        self.marks = tuple(item[:2] for item in (self.shown[:1] + self.shown[-1:]))
        if self.watch_job is None and self.shown:
            try:
                self.watch_job = self.pane.after(WATCH_MS, self._watch)
            except Exception:
                self.watch_job = None

    def _watch(self):
        self.watch_job = None
        if not self.shown or self.job is not None:
            return
        try:
            now = tuple(box[:2] if box else None for box in self._sig())
        except Exception:
            return
        if now != self.marks:
            self.shown = []         # 置き直す（同じ見た目の比べを外す）
            self.refresh()
            return
        self._watch_start()

    def clear(self):
        for name in ('job', 'watch_job'):
            job = getattr(self, name)
            setattr(self, name, None)
            if job is not None:
                try:
                    self.pane.after_cancel(job)
                except Exception:
                    pass
        if self.shown:          # 置いてある時だけ外す（掴んで動かしている間の2回目からは何もしない）
            for label in self.labels[:len(self.shown)]:
                try:
                    label.place_forget()
                except Exception:
                    pass
        self.shown = []


def for_overview(ov, shown):
    """縮小に入った時: 見せている分身ごとに PeerEmoji を用意して、MOVE_QUIET_MS 後に重ねる。"""
    if not on():
        return
    keep = getattr(ov, '_peer_emoji', None)
    if keep is None:
        keep = ov._peer_emoji = {}
    for pane, name, _back in shown:
        got = keep.get(name)
        if got is None or got.pane is not pane:
            got = keep[name] = PeerEmoji(pane, name)
        got.moving()        # 入った直後ではなく少し後に（入る時の重さに足さない・すぐ掴んで動かせば取り消す）


def moved(ov):
    for got in (getattr(ov, '_peer_emoji', None) or {}).values():
        if got.shown or got.job is not None or _any_emoji(got):
            got.moving()


def _any_emoji(got):
    try:
        w = int(got.tk.call('winfo', 'width', got.name))
        h = int(got.tk.call('winfo', 'height', got.name))
        return bool(got.pieces('@0,0', '@%d,%d' % (w, h)))      # 見えている所だけ（絞っている時はその行だけ）
    except Exception:
        return False


def off(ov):
    for got in (getattr(ov, '_peer_emoji', None) or {}).values():
        got.clear()
