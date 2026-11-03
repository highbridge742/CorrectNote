# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""マウスの2つの操作（2026-10-30 うにさん）。

1. 右ボタンを押したまま左クリック: 範囲を選んでいればコピー、選んでいなければ貼り付け（カーソルの位置へ）。
   右を離したときに候補一覧を出さない（app._mouse_chord を見て止める）。
2. 左ダブルクリックで**語だけ**を選ぶ（Windows のメモ帳のように）。Tk の語は空白で区切るので、日本語の行では
   行の全部が選ばれていた。語は形態素解析の区切り（無ければ字の種類の切れ目）。そのまま左を押して動かすと、
   語の単位で選択を広げる。

欄の bindtags の先頭に CnMouse を差し込み、Tk の Text の動き（クラスの束縛）より先に受ける。
"""
import re
import tkinter as tk
from types import SimpleNamespace

TAG = 'CnMouse'
BUTTON3_MASK = 0x400


def install(app, widget, editable=True):
    tags = widget.bindtags()
    if TAG not in tags:
        widget.bindtags((TAG,) + tuple(tags))
    widget._cn_mouse_editable = editable
    if getattr(app, '_cn_mouse_bound', False):
        return
    app._cn_mouse_bound = True
    root = app.root
    root.bind_class(TAG, '<ButtonPress-1>', lambda e: _press(app, e))
    root.bind_class(TAG, '<Double-Button-1>', lambda e: _double(app, e))
    root.bind_class(TAG, '<B1-Motion>', lambda e: _motion(app, e))
    root.bind_class(TAG, '<ButtonRelease-1>', lambda e: _release(app, e))


# --- 右を押しながら左 ----------------------------------------------------
def _press(app, event):
    app._word_drag = None
    if not int(getattr(event, 'state', 0) or 0) & BUTTON3_MASK:
        return None
    w = event.widget
    app._mouse_chord = True          # 右の離しで候補一覧を出さない（_on_editor_right_click 等）
    try:
        selected = w.tag_ranges('sel')
    except tk.TclError:
        return 'break'
    if selected:
        copy = getattr(app, '_copy_focused_selection', None)
        if copy is not None:
            copy(SimpleNamespace(widget=w))
    elif getattr(w, '_cn_mouse_editable', True) and str(w.cget('state')) == 'normal':
        try:
            w.focus_set()
            w.event_generate('<<Paste>>')
        except tk.TclError:
            pass
    return 'break'


def take_chord(app):
    """右の離しが「右を押しながら左」の終わりなら True（一度だけ）。"""
    chord = bool(getattr(app, '_mouse_chord', False))
    app._mouse_chord = False
    return chord


# --- 語の単位の選択 --------------------------------------------------------
_KINDS = (('kanji', re.compile('[㐀-鿿豈-﫿々〆ヶ]')),
          ('hiragana', re.compile('[ぁ-ゟ]')),
          ('katakana', re.compile('[゠-ヿｦ-ﾟー]')),
          ('latin', re.compile(r'[0-9A-Za-z_０-９Ａ-Ｚａ-ｚ\'’]')),
          ('space', re.compile(r'[\s　]')))


def _kind(ch):
    for name, pattern in _KINDS:
        if pattern.match(ch):
            return name
    return 'other:' + ch


def word_at(line, col):
    """line の col 文字目を含む語の [start, end)。形態素の区切りを使い、英数字の連なりは1語にまとめる。"""
    if not line:
        return 0, 0
    col = max(0, min(col, len(line) - 1))
    kind = _kind(line[col])
    if kind in ('latin', 'space'):
        start = col
        while start > 0 and _kind(line[start - 1]) == kind:
            start -= 1
        end = col + 1
        while end < len(line) and _kind(line[end]) == kind:
            end += 1
        return start, end
    try:
        from morphology import tokenize
        for token in tokenize(line):
            if token.start <= col < token.end:
                return token.start, token.end
    except Exception:
        pass
    if kind.startswith('other:'):
        return col, col + 1
    start = col
    while start > 0 and _kind(line[start - 1]) == kind:
        start -= 1
    end = col + 1
    while end < len(line) and _kind(line[end]) == kind:
        end += 1
    return start, end


def _word_range(w, index):
    row = int(w.index(index).split('.')[0])
    line = w.get('%d.0' % row, '%d.end' % row)
    col = len(w.get('%d.0' % row, index))
    if col >= len(line) and line:
        col = len(line) - 1
    a, z = word_at(line, col)
    return row, a, z


def _set(w, row1, a, row2, z, insert_at_end=True):
    first, last = '%d.0+%dc' % (row1, a), '%d.0+%dc' % (row2, z)
    w.tag_remove('sel', '1.0', 'end')
    w.tag_add('sel', first, last)
    w.mark_set('insert', last if insert_at_end else first)


def _double(app, event):
    w = event.widget
    try:
        row, a, z = _word_range(w, '@%d,%d' % (event.x, event.y))
        if a == z:
            return None
        _set(w, row, a, row, z)
        w.mark_set('tk::anchor1', '%d.0+%dc' % (row, a))
    except tk.TclError:
        return None
    app._word_drag = dict(widget=w, row=row, start=a, end=z)
    return 'break'


def _motion(app, event):
    drag = getattr(app, '_word_drag', None)
    w = event.widget
    if not drag or drag['widget'] is not w:
        return None
    try:
        row, a, z = _word_range(w, '@%d,%d' % (event.x, event.y))
        if (row, a) < (drag['row'], drag['start']):
            _set(w, row, a, drag['row'], drag['end'], insert_at_end=False)
        else:
            _set(w, drag['row'], drag['start'], row, max(z, a))
        w.see('insert')
    except tk.TclError:
        pass
    return 'break'


def _release(app, event):
    app._word_drag = None
    return None
