# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Text 以外の部品にも絵文字を色付きで出す（2026-11-21 09:56Z うにさん「絵文字を白黒で見せないようにする」）。

emoji_color の色付けは tk.Text（メモ欄・補正欄・簡易入力）に重ねる形で、候補の一覧（Listbox）・タブの名（Label）・
行の状態の表などには届かず、Tk の白黒の字のままだった。
・label(widget): Label の字に絵文字があれば、字ごと色付きの絵（emoji_color.line_image）にして見せる（字はそのまま持つ）
・listbox(widget): Listbox の見えている行のうち絵文字のある行に、その行を色付きで描いた絵を重ねる。選んでいる行は
  選んだ色の地で描き直す。重ねた絵の上のクリック・ホイールは一覧へそのまま渡す（選ぶ・決める・動かすは今まで通り）
・text(widget): Text（行の状態の表など）に emoji_color.install を掛ける
どれも絵文字の無い所では何もしない。CN_EMOJI_WIDGETS=0 で前の形（白黒）
"""
import os
import tkinter as tk

POLL_MS = 150
FORWARD = ('<ButtonPress-1>', '<ButtonRelease-1>', '<Double-Button-1>', '<B1-Motion>', '<Motion>',
           '<ButtonPress-3>', '<ButtonRelease-3>', '<MouseWheel>', '<Enter>', '<Leave>')


def on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_EMOJI_WIDGETS') != '0'


def _has_emoji(text):
    try:
        from emoji_color import emoji_spans
        return bool(emoji_spans(text or ''))
    except Exception:
        return False


def _hex(widget, color):
    """色の名（white・SystemButtonFace など）を #rrggbb に（emoji_color の描き手は #rrggbb だけを読む）。"""
    try:
        r, g, b = widget.winfo_rgb(color)
        return '#%02x%02x%02x' % (r // 257, g // 257, b // 257)
    except (tk.TclError, ValueError):
        return '#000000'


def _image(master, text, font, fg, bg, height):
    try:
        from emoji_color import line_image
        return line_image(master, text, font, _hex(master, fg), _hex(master, bg), height)
    except Exception:
        return None


def label(widget):
    """Label の字に絵文字があれば、色付きの絵で見せる。出したら True。"""
    if not on():
        return False
    try:
        text = str(widget.cget('text'))
        if not _has_emoji(text):
            if getattr(widget, '_cn_emoji_image', None) is not None:
                widget.configure(image='')          # 絵文字が無くなった: 字に戻す
                widget._cn_emoji_image = None
            return False
        from tkinter import font as tkfont
        font = widget.cget('font')
        f = tkfont.Font(root=widget, font=font)
        height = int(f.metrics('linespace')) + 2
        fg = str(widget.cget('fg'))
        img = _image(widget, text, font, fg, str(widget.cget('bg')), height)
        if img is None:
            return False
        if f.actual('underline'):                   # 下線の字（目次）は絵にも下線を引く
            y = min(height - 1, int(f.metrics('ascent')) + 2)
            img.put(_hex(widget, fg), to=(0, y, int(img.width()), y + 1))
        widget.configure(image=img, compound='none')
        widget._cn_emoji_image = img            # 絵を手放さない
        return True
    except tk.TclError:
        return False


def text(widget):
    if not on():
        return False
    try:
        from emoji_color import install
        install(widget)
        return True
    except Exception:
        return False


class ListboxEmoji:
    def __init__(self, lb):
        self.lb = lb
        self.shown = {}         # 行 → (かぎ, Label)
        self.job = None
        self.size = -1
        self.any = False
        try:
            lb.bind('<<ListboxSelect>>', lambda e: self.refresh(), add='+')
            lb.bind('<Configure>', lambda e: self.refresh(), add='+')
            lb.bind('<Destroy>', lambda e: self.stop() if e.widget is lb else None, add='+')
        except tk.TclError:
            pass
        self.schedule(1)

    def stop(self):
        job, self.job = self.job, None
        if job is not None:
            try:
                self.lb.after_cancel(job)
            except tk.TclError:
                pass

    def schedule(self, ms=POLL_MS):
        if self.job is not None:
            return
        try:
            self.job = self.lb.after(ms, self._tick)
        except tk.TclError:
            self.job = None

    def _tick(self):
        self.job = None
        try:
            if not int(self.lb.winfo_exists()):
                return
        except tk.TclError:
            return
        self.refresh()
        if self.any:
            self.schedule()             # 動かした・選んだのを追う（絵文字の行がある時だけ）

    def _bg_fg(self, i):
        lb = self.lb
        if lb.selection_includes(i):
            return str(lb.cget('selectbackground')), str(lb.cget('selectforeground'))
        try:
            bg = str(lb.itemcget(i, 'background')) or str(lb.cget('bg'))
            fg = str(lb.itemcget(i, 'foreground')) or str(lb.cget('fg'))
        except tk.TclError:
            bg, fg = str(lb.cget('bg')), str(lb.cget('fg'))
        return bg, fg

    def refresh(self):
        lb = self.lb
        try:
            n = lb.size()
            if n != self.size:
                self.size = n
                self.any = any(_has_emoji(lb.get(i)) for i in range(n))
            if not self.any:
                self._drop_all()
                return
            first = lb.nearest(0)
            last = lb.nearest(lb.winfo_height())
            wanted = {}
            for i in range(max(0, first), min(n - 1, last) + 1):
                item = lb.get(i)
                if not _has_emoji(item):
                    continue
                box = lb.bbox(i)
                if not box:
                    continue
                bg, fg = self._bg_fg(i)
                wanted[i] = ((item, bg, fg, tuple(box), lb.winfo_width()), box, bg, fg, item)
            for i in list(self.shown):
                if i not in wanted:
                    self._drop(i)
            for i, (key, box, bg, fg, item) in wanted.items():
                old = self.shown.get(i)
                if old is not None and old[0] == key:
                    continue
                x, y, _w, h = box
                img = _image(lb, item, lb.cget('font'), fg, bg, h)
                if img is None:
                    self._drop(i)
                    continue
                if old is not None:
                    lab = old[1]                # 同じ絵を差し替える（押している間に壊すと、離したのが一覧へ届かない）
                    lab.configure(image=img, bg=bg)
                else:
                    lab = tk.Label(lb, image=img, bd=0, highlightthickness=0, bg=bg, anchor='w')
                    for seq in FORWARD:
                        lab.bind(seq, lambda e, s=seq, lab=lab: self._forward(e, s, lab))
                lab._cn_emoji_image = img
                lab.place(x=x, y=y, height=h, width=max(1, lb.winfo_width() - x - 2))
                self.shown[i] = (key, lab)
        except tk.TclError:
            pass

    def _forward(self, event, seq, lab):
        lb = self.lb
        try:
            x = int(event.x) + int(lab.winfo_x())
            y = int(event.y) + int(lab.winfo_y())
            options = dict(x=x, y=y, rootx=int(event.x_root), rooty=int(event.y_root))
            if seq == '<MouseWheel>':
                options['delta'] = int(getattr(event, 'delta', 0))
            if seq in ('<Enter>', '<Leave>'):
                return None
            lb.event_generate(seq.replace('ButtonPress', 'Button'), **options)
        except tk.TclError:
            pass
        self.refresh()
        return 'break'

    def _drop(self, i):
        got = self.shown.pop(i, None)
        if got is not None:
            try:
                got[1].destroy()
            except tk.TclError:
                pass

    def _drop_all(self):
        for i in list(self.shown):
            self._drop(i)


def listbox(widget):
    """Listbox に絵文字の色付けを掛ける（掛けたら ListboxEmoji）。"""
    if not on():
        return None
    try:
        got = ListboxEmoji(widget)
        widget._cn_emoji_listbox = got
        return got
    except Exception:
        return None
