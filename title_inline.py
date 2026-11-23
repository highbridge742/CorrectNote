# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""タイトルと目次を、本文の Text の中の本物の字（先頭の見出しの行）として置く形（2026-11-15 うにさん「本文と目次が同じ
仕組みの中で動くことはできないのか。タイトルも描画するならそうしたほうがよい」）。

- 見出しは本文の欄（と分割の右の補正欄）の先頭の H 行: タイトル1行・目次の行（目次があれば、その数だけ）・下の線1行。
  隠した行は持たない（隠した行をまたぐと Tk の行送りのスクロールが止まった・2026-11-15 うにさん「下から右ドラッグ
  スクロールで1行目に到達すると、目次で引っ掛かってスクロールが止まる」）。目次の数が変わって H が変わる時は、Tk の
  Undo の控え（生の行番号）がずれるので、控えをタブの切り替えと同じ道で預かって返す（_resized）。
- 分割の右（補正欄）には見出しの字を出さない（2026-11-15 うにさん「タイトルと目次は、分割表示の時は左側だけでよい」）。
  左右の本文の行がそろうよう、右には同じ高さの空きだけを置く。空の行だと、左の字が使う代わりの字体（漢字・数字）の
  分だけ左の行が高くなりそろわなかったので（20px と 17px）、右にも同じ字を置き、欄の地の色で塗って見えなくする
  （選んでも見えない・線・下線なし・反応なし。写す道は本文の頭へ寄せるので字は写らない）。行は折り返さない。
- アプリと Tk の決まりごとは body_index の変換を通して呼ぶので、1行目＝本文の1行目のまま（保存・解析・補正・
  ブックマーク・検索・Undo・行番号はそのまま）。見出しを書くのは生の命令（Undo に積まない・変更の印を立てない）。
- スクロール・描画・テーマは Text 自身。重ねる窓・描き直し・画素送りは要らない。
- タイトルはタイトルの行そのもので直に打つ（重ねる欄は出さない）。カーソルがタイトルの行にある間だけ、本文の欄の
  キー（IME の確定・ペースト・BackSpace・矢印など）を、見えないタイトルの Text（TitleToc.title＝字・Undo 1列・品詞の
  控え）へ Tk 自身の Text の手続きで入れ、その字とカーソル・選択をすぐタイトルの行へ写す。本文の欄の束縛
  （打鍵の記録・解析・補正）はその間は走らない（前の重ねる形でタイトルの欄に焦点があった時と同じ）。
- 目次の行のクリックは本文のその行へ飛ぶ。補正欄の側の目次は反応しない。
- 既定（2026-11-15 から）。CN_TITLE_TOC_INLINE=0 で前の重ねる形。
"""
import os
import tkinter as tk
from contextlib import contextmanager

import body_index
import title_toc as T

ENV = 'CN_TITLE_TOC_INLINE'
TAG_HEAD = 'cn_head'
TAG_TITLE = 'cn_head_title'
TAG_LINK = 'cn_head_link'
TAG_RULE = 'cn_head_rule'
# 右（補正欄）の空の見出し: 字の大きさ（行の高さ）だけ同じ
TAG_TITLE_BLANK = 'cn_head_title_blank'
TAG_LINK_BLANK = 'cn_head_link_blank'
TAG_RULE_BLANK = 'cn_head_rule_blank'
_ALL_TAGS = (TAG_HEAD, TAG_TITLE, TAG_LINK, TAG_RULE, TAG_TITLE_BLANK, TAG_LINK_BLANK, TAG_RULE_BLANK)
BIND_TAG = 'CorrectNoteHead'
TITLE_KEYS = 'CorrectNoteTitleKeys'   # タイトルの行で打つ間: Text のクラスのキーの手続きを、見えないタイトルの Text で走らせる
KEY_STOP = 'CorrectNoteKeyStop'       # タイトルの行で打つ間: キーをここで止める（本文の欄・Text のクラスへ流さない）


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    # 2026-11-15 から既定（うにさんの求めた形）。CN_TITLE_TOC_INLINE=0 で重ねる形
    return T.enabled(environ) and environ.get(ENV) != '0'


def _raw(widget, *args):
    return widget.tk.call(widget._cn_body_raw, *args)


def toc_count(widget):
    """見出しにある目次の行の数。"""
    return len(getattr(widget, '_cn_head_texts', ()) or ()) and max(0, head_rows(widget) - 2)


def head_rows(widget):
    """見出しの行数 H（変換を掛けていない欄は 0）。"""
    return body_index.height(widget)


def _writer(widget):
    """見出しの字を書く、見えない分身（peer）の名前。"""
    name = getattr(widget, '_cn_head_writer', None)
    if name:
        return name
    name = widget._w + '_cn_head_writer'
    opts = []
    for key in ('-undo', '-autoseparators', '-maxundo'):     # Undo の決まりは分身と1つ。今の値のまま作る
        opts += [key, _raw(widget, 'cget', key)]
    _raw(widget, 'peer', 'create', name, '-state', 'normal', *opts)
    # Tk は Undo の一手を、いちばん新しい分身の名前で控える（insert・delete を「分身の名前 生の位置」で呼び返す）。
    # そのまま分身が受けると、字は戻るが本文の欄の観察者（undo_feedback の色・tab_undo・解析）を素通りした
    # （2026-11-15 tests_gui_undo_feedback）。分身の名前は、生の位置を本文の位置に直して本文の欄の命令へ回す口にし、
    # 見出しを書くのは名前を替えた本物（_cn_head_writer）から（doc_window.route_edits と同じ考え）
    real = name + '_real'
    widget.tk.call('rename', name, real)

    def route(*args):
        args = body_index.untranslate(args, head_rows(widget))
        return widget.tk.call(widget._w, *args)
    widget.tk.createcommand(name, route)
    widget._cn_head_writer = real

    def gone(event, name=name):
        if event.widget is widget:
            try:
                widget.tk.call('destroy', name)
            except tk.TclError:
                pass
            try:
                widget.tk.deletecommand(name)
            except tk.TclError:
                pass
    widget.bind('<Destroy>', gone, add=True)
    return real


@contextmanager
def _quiet(widget):
    """見出しの字を書く間: Undo に積まない・変更の印を立てない。書くのは見えない分身から（読み取り専用の補正欄も
    configure しない）。Undo を外すのも分身の configure で（-undo は分身と1つ）。本文の欄を configure すると欄の全部を
    組み直して1回 22ms かかり、タブを替えるたびに4回・タイトルを打つたびに2回あった（2026-11-15 測った）。"""
    w = _writer(widget)
    undo = int(_raw(widget, 'cget', '-undo'))
    modified = _raw(widget, 'edit', 'modified')
    if undo:
        widget.tk.call(w, 'configure', '-undo', 0)
    try:
        yield w
    finally:
        if undo:
            widget.tk.call(w, 'configure', '-undo', 1)
        _raw(widget, 'edit', 'modified', modified)


def prepare(widget):
    """Text を作った直後（行番号の列などが命令を包む前）に呼ぶ。変換を掛け、空の見出し（タイトルの行1行）を置く。"""
    body_index.install(widget, 1)
    write(widget, '', [])
    return widget


def _texts(title, entries, blank):
    rows = [T.one_line(title)] + [str(e[2]) for e in entries]
    if entries:
        rows.append('')                  # 下の線の行（目次がある時だけ）
    return rows                          # 右（blank）も同じ字（高さをそろえる。地の色で見えなくする）


def write(widget, title, entries, blank=False):
    """見出しの行を書く（変わった行だけ）。entries: [(飛ぶ行, 見せる行, 字)]。Undo に積まず、変更の印も立てない。
    blank=True は右（補正欄）の空の見出し（同じ行の数・同じ高さ・字なし）。見出しの行の数 H が変わったら、その差を返す
    （ふだんは 0）。"""
    if not getattr(widget, '_cn_body_raw', None):
        return 0
    entries = list(entries)
    texts = _texts(title, entries, blank)
    h = len(texts)
    changed = 0
    with _quiet(widget) as w:
        ready = getattr(widget, '_cn_head_ready', False)
        old = head_rows(widget) if ready else 0
        if not ready:
            widget.tk.call(w, 'insert', '1.0', '\n'.join(texts) + '\n')
            body_index.set_height(widget, h)
            widget._cn_head_ready = True
        elif old != h:
            # 目次の数が変わった: 見出しを作り直す（本文の行は Tk の印・タグごと、そのまま下へ・上へ動く）
            widget.tk.call(w, 'delete', '1.0', '%d.0' % (old + 1))
            widget.tk.call(w, 'insert', '1.0', '\n'.join(texts) + '\n')
            body_index.set_height(widget, h)
            changed = h - old
        else:
            # 前に書いた字（控え）と違う行だけ書き換える（打つたびに全部の行を読まない）
            known = getattr(widget, '_cn_head_texts', None)
            for row, text in enumerate(texts, 1):
                if known is not None and row <= len(known) and known[row - 1] == text:
                    continue
                if str(_raw(widget, 'get', '%d.0' % row, '%d.end' % row)) != text:
                    widget.tk.call(w, 'delete', '%d.0' % row, '%d.end' % row)
                    if text:
                        widget.tk.call(w, 'insert', '%d.0' % row, text)
        widget._cn_head_texts = texts
        widget._cn_head_blank = blank
        title_tag, link_tag, rule_tag = ((TAG_TITLE_BLANK, TAG_LINK_BLANK, TAG_RULE_BLANK) if blank
                                         else (TAG_TITLE, TAG_LINK, TAG_RULE))
        n = len(entries)
        for tag in _ALL_TAGS:
            _raw(widget, 'tag', 'remove', tag, '1.0', '%d.0' % (h + 1))
        _raw(widget, 'tag', 'add', TAG_HEAD, '1.0', '%d.0' % (h + 1))
        _raw(widget, 'tag', 'add', title_tag, '1.0', '2.0')
        if n:
            # 字の行は字だけに（下線を改行に付けない。空の行は改行に字の大きさを付けて高さをそろえる）
            ends = ['%d.end' % row if texts[row - 1] else '%d.0' % (row + 1) for row in range(2, n + 2)]
            _raw(widget, 'tag', 'add', link_tag, *[p for row, end in zip(range(2, n + 2), ends) for p in ('%d.0' % row, end)])
            _raw(widget, 'tag', 'add', rule_tag, '%d.0' % h, '%d.0' % (h + 1))
        if blank:
            for tag in (TAG_TITLE_BLANK, TAG_LINK_BLANK, TAG_RULE_BLANK):
                _raw(widget, 'tag', 'raise', tag)        # 品詞の色より上（字を地の色で塗る）
    widget._cn_head_rows = [e[0] for e in entries]
    return changed


def style(widget, family, link_size, link_color, rule_color):
    # 見出しの行は折り返さない（左右で同じ高さにする。右は字が無いので折り返さない）
    _raw(widget, 'tag', 'configure', TAG_TITLE, '-font', (family, T.TITLE_SIZE), '-wrap', 'none')
    _raw(widget, 'tag', 'configure', TAG_LINK, '-font', (family, link_size, 'underline'), '-foreground', link_color,
         '-wrap', 'none')
    _raw(widget, 'tag', 'configure', TAG_RULE, '-font', (family, 1), '-background', rule_color)
    # 右の空きは字を欄の地の色で塗る（選んでも見えない）
    ground = str(_raw(widget, 'cget', '-background'))
    hide = ('-foreground', ground, '-selectforeground', ground, '-selectbackground', ground, '-background', '')
    _raw(widget, 'tag', 'configure', TAG_TITLE_BLANK, '-font', (family, T.TITLE_SIZE), '-wrap', 'none', *hide)
    _raw(widget, 'tag', 'configure', TAG_LINK_BLANK, '-font', (family, link_size), '-wrap', 'none', *hide)
    _raw(widget, 'tag', 'configure', TAG_RULE_BLANK, '-font', (family, 1), *hide)
    # 目次と本文の境目の線は、補正欄（右）にも同じ位置・同じ見た目で引く（2026-11-20 うにさん「目次と本文の境目の線は、
    # 補正欄側にも表示する」）。右の見出しは同じ高さの空の行なので、その行の地を線の色にするだけ。CN_TOC_RULE_RIGHT=0 で前の形
    if os.environ.get('CN_TOC_RULE_RIGHT') != '0':
        _raw(widget, 'tag', 'configure', TAG_RULE_BLANK, '-background', rule_color)


def copy_pos_tags(widget, source, blank=False):
    """タイトルの品詞の倍率と色（TitleToc.title に付いたタグ）を、見出しのタイトルの行へ写す。blank: 右の空き（字の
    大きさだけ効かせ、色は空きのタグで地の色に塗る）。"""
    for tag in source.tag_names():
        if not tag.startswith('cn_title_pos_'):
            continue
        opts = []
        for key in ('font', 'foreground'):
            value = source.tag_cget(tag, key)
            if value:
                opts += ['-' + key, value]
        if opts:
            _raw(widget, 'tag', 'configure', tag, *opts)
        _raw(widget, 'tag', 'remove', tag, '1.0', '2.0')
        ranges = source.tag_ranges(tag)
        for a, b in zip(ranges[::2], ranges[1::2]):
            _raw(widget, 'tag', 'add', tag, str(a), str(b))
    if blank:
        _raw(widget, 'tag', 'raise', TAG_TITLE_BLANK)


def write_title(widget, title):
    """タイトルの行（1行目）だけ書く（打つたびはこちら。目次の行は見ない）。右の空きにも同じ字（見えない）。"""
    if not getattr(widget, '_cn_head_ready', False):
        return
    text = T.one_line(title)
    if str(_raw(widget, 'get', '1.0', '1.end')) == text:
        return
    with _quiet(widget) as w:
        widget.tk.call(w, 'delete', '1.0', '1.end')
        if text:
            widget.tk.call(w, 'insert', '1.0', text)
        _raw(widget, 'tag', 'add', TAG_HEAD, '1.0', '2.0')
        _raw(widget, 'tag', 'add', TAG_TITLE_BLANK if getattr(widget, '_cn_head_blank', False) else TAG_TITLE, '1.0', '2.0')


def _is_key_seq(seq):
    if seq.startswith('<<'):
        return seq != '<<PasteSelection>>'
    return 'Key' in seq and 'Button' not in seq and 'Motion' not in seq and 'Wheel' not in seq


_PCT = __import__('re').compile(r'%(.)')


def bind_title_keys(widget):
    """TITLE_KEYS と KEY_STOP の束縛を作る（1つの Tk に1度）。TITLE_KEYS は Text のクラスのキーの束縛を写し、
    手続きの %W を、その時の見えないタイトルの Text（widget._cn_title_model）に替えて走らせる。"""
    tk_ = widget.tk
    if tk_.splitlist(tk_.call('bind', TITLE_KEYS)):
        return
    for seq in tk_.splitlist(tk_.call('bind', 'Text')):
        if not _is_key_seq(str(seq)):
            continue
        script = str(tk_.call('bind', 'Text', seq))
        widget.bind_class(TITLE_KEYS, seq, lambda e, s=script: run_text_script(e, s))
    widget.bind_class(KEY_STOP, '<KeyPress>', lambda e: 'break')
    widget.bind_class(KEY_STOP, '<KeyRelease>', lambda e: 'break')


def run_text_script(event, script):
    """Text のクラスの手続きを、本文の欄に来たキーで、見えないタイトルの Text に走らせる。"""
    widget = event.widget
    model = getattr(widget, '_cn_title_model', None)
    if model is None:
        return None
    tk_ = widget.tk
    tk_.setvar('::cn_title_A', event.char or '')

    def sub(m):
        c = m.group(1)
        if c == 'W':
            return str(model)
        if c == 'A':
            return '$::cn_title_A'
        if c == 'x':
            return str(event.x)
        if c == 'y':
            return str(event.y)
        if c == '%':
            return '%'
        return '{}'
    try:
        tk_.eval('catch {%s}' % _PCT.sub(sub, script))
    except tk.TclError:
        pass
    return None


def fits_from_top(widget, index):
    """文書の頭（見出しの上）から見せても、本文の位置 index の行が欄に収まるか（目次で頭に近い所へ飛ぶ時は、頭から
    見せて目次も見えたままにする・2026-11-15 うにさん「目次クリックで目次付近にジャンプすると、目次が表示されない」）。"""
    raw = getattr(widget, '_cn_body_raw', None)
    if not raw or not head_rows(widget):
        return False
    try:
        row = int(str(index).split('.')[0]) + head_rows(widget)
        above = widget.tk.call(raw, 'count', '-update', '-ypixels', '1.0', '%d.0' % row)
        above = int(above[0] if isinstance(above, tuple) else above or 0)
        line = int(widget.tk.call('font', 'metrics', widget.cget('font'), '-linespace'))
        edge = 2 * sum(int(float(str(widget.cget(k)))) for k in ('pady', 'borderwidth', 'highlightthickness'))
        return above + 2 * line <= widget.winfo_height() - edge
    except (tk.TclError, ValueError, TypeError):
        return False


def top_in_header(widget):
    """欄のいちばん上に見えているのが見出しの行か（行番号の列は番号を描かない・左右の欄は生の位置で揃える）。"""
    raw = getattr(widget, '_cn_body_raw', None)
    if not raw:
        return False
    try:
        return int(str(widget.tk.call(raw, 'index', '@0,0')).split('.')[0]) <= head_rows(widget)
    except (tk.TclError, ValueError):
        return False


def sync_header_view(src, dst):
    """左の欄の上に見出しが見えている間は、右の欄も同じ生の位置・同じ画素に揃える（見出しは左右で同じ行数・同じ字）。
    揃えたら True。本文だけが見えている時は False（今まで通り行で揃える）。"""
    if not top_in_header(src) or head_rows(src) != head_rows(dst) or not getattr(dst, '_cn_body_raw', None):
        return False
    try:
        top = str(src.tk.call(src._cn_body_raw, 'index', '@0,0'))
        dst.tk.call(dst._cn_body_raw, 'yview', top)
        a = src.tk.call(src._cn_body_raw, 'dlineinfo', top)
        b = dst.tk.call(dst._cn_body_raw, 'dlineinfo', top)
        if a and b and int(b[1]) != int(a[1]):
            dst.tk.call(dst._cn_body_raw, 'yview', 'scroll', int(b[1]) - int(a[1]), 'pixels')
    except (tk.TclError, ValueError, IndexError):
        return False
    return True


def header_row(widget, x, y):
    """欄の (x, y) が見出しの中なら、その生の行（1〜H）。本文なら None。"""
    try:
        row = int(str(_raw(widget, 'index', '@%d,%d' % (x, y))).split('.')[0])
    except (tk.TclError, ValueError):
        return None
    return row if row <= head_rows(widget) else None


class InlineTitleToc(T.TitleToc):
    """見出しを本文の中の字として置く形。タイトルの字・Undo・品詞の控えは、見えない TitleToc の欄（タイトルの Text）が持つ。
    打つのはタイトルの行そのもの（本文の欄に焦点・カーソルはタイトルの行の生の位置）。"""

    def __init__(self, app):
        super().__init__(app)
        self.inline = True
        self._active = False
        self._saved_tags = None
        self._drag = False
        self._sync_after = None
        editor = app.editor
        editor._cn_title_model = self.title
        bind_title_keys(editor)
        tags = tuple(t for t in editor.bindtags() if t != BIND_TAG)
        editor.bindtags((BIND_TAG,) + tags)
        editor.bind_class(BIND_TAG, '<Button-1>', self._click)
        editor.bind_class(BIND_TAG, '<Double-Button-1>', self._double)
        editor.bind_class(BIND_TAG, '<Triple-Button-1>', self._triple)
        editor.bind_class(BIND_TAG, '<Shift-Button-1>', self._shift_click)
        editor.bind_class(BIND_TAG, '<B1-Motion>', self._b1_motion)
        editor.bind_class(BIND_TAG, '<ButtonRelease-1>', self._release)
        editor.bind_class(BIND_TAG, '<Motion>', self._motion)
        editor.bind_class(BIND_TAG, '<KeyPress>', self._key)
        editor.bind_class(BIND_TAG, '<Down>', self._down)
        self._style_inline()
        self.render()

    # 見出しを書く ----------------------------------------------------------
    def panes(self):
        return [p for p in super().panes() if getattr(p, '_cn_body_raw', None)]

    def render(self):
        entries = self._entries or []
        editor = getattr(self.app, 'editor', None)
        for pane in self.panes():
            # 本文の欄だけに字。補正欄（分割の右）は同じ高さの空の見出し（2026-11-15 うにさん「タイトルと目次は、
            # 分割表示の時は左側だけでよい」）
            blank = pane is not editor
            changed = write(pane, self.get_title(), entries, blank=blank)
            copy_pos_tags(pane, self.title, blank=blank)
            if changed and pane is editor:
                self._resized(changed)
        self._show_caret()

    def _resized(self, rows):
        """目次の数が変わって見出しの行の数が変わった（本文の欄）。Tk 自身の Undo の控えは生の行番号なので、その分ずれる。
        タブを替えて戻る時と同じに、控えを本文の位置の形（undo_feedback）で預かり、Tk の控えを空にしてから返す
        （次の Ctrl+Z で、預かった一手を本文の位置から作り直して戻す・tab_undo と同じ道）。"""
        self.resized_count = getattr(self, 'resized_count', 0) + 1
        editor = self.app.editor
        feedback = getattr(getattr(self.app, '_tab_undo', None), 'feedback', None)
        snapshot = None
        if feedback is not None:
            try:
                snapshot = feedback.take()
            except Exception:
                snapshot = None
        try:
            editor.edit_reset()
        except tk.TclError:
            pass
        if snapshot is not None:
            try:
                feedback.give(snapshot)
            except Exception:
                pass

    def _style_inline(self):
        if not self._colors:
            return
        color = self._link_color()
        for pane in self.panes():
            style(pane, self._family(), self._toc_size(), color, self._rule_color())

    def restyle(self):
        super().restyle()
        if getattr(self, 'inline', False):
            self._style_inline()

    def refresh_toc(self, force=False, layout=True):
        try:
            lines = self.app.editor_source_text().split('\n')
        except Exception:
            lines = []
        entries = T.toc_entries(lines, getattr(self.app, 'bookmarks', ()))
        if entries == self._entries and not force:
            return False
        self._entries = entries
        self.render()
        return True

    def paint_pos(self, layout=True):
        super().paint_pos(layout=False)
        if getattr(self, 'inline', False):
            editor = getattr(self.app, 'editor', None)
            for pane in self.panes():
                write_title(pane, self.get_title())
                copy_pos_tags(pane, self.title, blank=pane is not editor)
            self._show_caret()

    # 重ねる形の部分は使わない ------------------------------------------------
    def ensure_pad(self):
        return

    def layout(self):
        return

    def position(self):
        return

    def _place_mirror(self, right, total):
        return

    def jump(self, row):
        """目次の行から本文のその行へ。頭から見せても飛び先が欄に収まるなら、頭から見せて目次も見えたままにする
        （2026-11-15 うにさん「目次クリックで目次付近にジャンプすると、目次が表示されない」）。収まらない時は今まで通り
        （飛び先を真ん中に）。ブックマークの移動など、ほかの飛び方は変えない。"""
        go = getattr(self.app, '_goto_line', None)
        if go is None:
            return
        editor = getattr(self.app, 'editor', None)
        if editor is not None and fits_from_top(editor, '%d.0' % row):
            go(row, stay_at_top=True)
        else:
            go(row)
        try:
            editor.focus_set()
        except Exception:
            pass

    def _changed_now(self):
        self._after = None
        self.refresh_toc()

    def switched(self, title):
        pending = getattr(self, '_after', None)
        if pending is not None:
            try:
                self.frame.after_cancel(pending)
            except tk.TclError:
                pass
            self._after = None
        self.leave_title()
        self.set_title(title, layout=False)
        self.refresh_toc(force=True)

    # タイトルの行で打つ --------------------------------------------------------
    def has_cursor(self):
        return bool(self._active)

    def typing_target(self, widget):
        """本文の欄へ入れようとした字（IME の絵文字など）の行き先。タイトルの行で打っている間はタイトル。"""
        if self._active and widget is getattr(self.app, 'editor', None):
            self._sync_soon()
            return self.title
        return widget

    def enter_title(self, col=None):
        editor = self.app.editor
        if not self._active:
            # 本文で続けていた括弧の巡回は、ほかの所をクリックした時と同じに確定する（このクリックは本文の欄の
            # クリックの束縛まで届かないので、ここで。tests_gui_shortcuts_menu・2026-11-16）
            forget = getattr(self.app, '_forget_bracket_cycle', None)
            if forget is not None:
                try:
                    forget()
                except Exception:
                    pass
            saved = tuple(t for t in editor.bindtags() if t != BIND_TAG)
            self._saved_tags = saved
            top = str(editor.winfo_toplevel())
            rest = tuple(t for t in saved if t not in (top, 'all'))
            # キー: 頭の束縛 → タイトルの Text の束縛（Return を止める・ペースト・Undo・コピー）→ Text の手続きをタイトルの
            # Text で → 窓・all（Ctrl+S・F2・F5 など、前に焦点がタイトルの欄にあった時と同じ）→ ここで止める。
            # マウスなどキー以外は、そのあと本文の欄の束縛へも流れる（ホイール・右ドラッグ）
            editor.bindtags((BIND_TAG, str(self.title), TITLE_KEYS, top, 'all', KEY_STOP) + rest)
            self._active = True
            self._title_last = True
            try:
                _raw(editor, 'tag', 'remove', 'sel', '1.0', 'end')
            except tk.TclError:
                pass
        if col is not None:
            self.title.mark_set('insert', '1.%d' % col)
            self.title.mark_set('tk::anchor' + str(self.title), 'insert')
            self.title.tag_remove('sel', '1.0', 'end')
        try:
            editor.focus_set()
        except tk.TclError:
            pass
        self._show_caret()

    def leave_title(self, insert=None):
        """タイトルの行から本文へ。insert: 本文のカーソルの位置（本文の位置・None ならそのまま／見出しにあれば本文の頭）。"""
        if not self._active:
            return
        editor = self.app.editor
        self._active = False
        self._title_last = False
        self._drag = False
        if self._saved_tags is not None:
            editor.bindtags((BIND_TAG,) + tuple(self._saved_tags))
            self._saved_tags = None
        try:
            self.title.tag_remove('sel', '1.0', 'end')
            _raw(editor, 'tag', 'remove', 'sel', '1.0', '%d.0' % (head_rows(editor) + 1))
            if insert is not None:
                editor.mark_set('insert', insert)
            elif self._raw_row(editor) <= head_rows(editor):
                editor.mark_set('insert', '1.0')
        except tk.TclError:
            pass

    def _raw_row(self, editor, index='insert'):
        try:
            return int(str(_raw(editor, 'index', index)).split('.')[0])
        except (tk.TclError, ValueError):
            return head_rows(editor) + 1

    def _show_caret(self):
        """タイトルの Text のカーソルと選択を、タイトルの行（生の位置）へ写す。"""
        if not getattr(self, '_active', False):
            return
        editor = self.app.editor
        try:
            col = str(self.title.index('insert')).split('.')[1]
            _raw(editor, 'mark', 'set', 'insert', '1.%s' % col)
            _raw(editor, 'tag', 'remove', 'sel', '1.0', '2.0')
            ranges = self.title.tag_ranges('sel')
            if ranges:
                a = str(ranges[0]).split('.')[1]
                b = str(ranges[-1]).split('.')[1]
                _raw(editor, 'tag', 'add', 'sel', '1.%s' % a, '1.%s' % b)
            _raw(editor, 'see', 'insert')
        except (tk.TclError, IndexError):
            pass

    def _sync(self):
        self._sync_after = None
        if not self._active:
            return
        editor = self.app.editor
        if self._raw_row(editor) != 1:
            # 元に戻すが本文の一手だった・アプリが本文の位置へ動かした: 本文へ
            self.leave_title(insert=None)
            return
        for pane in self.panes():
            write_title(pane, self.get_title())
        self._show_caret()

    def _sync_soon(self):
        if self._sync_after is None:
            try:
                self._sync_after = self.app.editor.after_idle(self._sync)
            except tk.TclError:
                self._sync_after = None

    def _key(self, event):
        if not self._active:
            return None
        editor = self.app.editor
        if self._raw_row(editor) != 1:
            # 本文へ移っていた（アプリの飛ぶ・Undo の本文の一手）: 本文の束縛へ戻し、同じキーを本文で打ち直す
            self.leave_title()
            try:
                if event.keysym and event.keysym != '??' and len(event.char or '') <= 1 and                         (not event.char or event.char.isascii()):
                    editor.event_generate('<KeyPress>', keysym=event.keysym, state=event.state, when='now')
                elif event.char:
                    editor.tk.call('tk::TextInsert', editor, event.char)
            except tk.TclError:
                pass
            return 'break'
        self._sync_soon()
        return None

    def _down(self, event):
        if not self._active:
            return None
        self.leave_title(insert='1.0')
        try:
            self.app.editor.see('insert')
        except tk.TclError:
            pass
        return 'break'

    # マウス ------------------------------------------------------------------
    def _col_at(self, event):
        editor = self.app.editor
        try:
            at = str(_raw(editor, 'index', '@%d,%d' % (event.x, event.y)))
        except tk.TclError:
            return None
        row, col = at.split('.')
        if int(row) == 1:
            return int(col)
        return len(self.get_title()) if int(row) > 1 else 0

    def _click(self, event):
        editor = self.app.editor
        row = header_row(editor, event.x, event.y)
        if row is None:
            if self._active:
                # 本文のクリック: 本文の束縛へ戻す。このクリックはそのまま本文の欄・Text の束縛へ流れる（キー以外は
                # KEY_STOP を通る）。同じクリックを作り直して送ると、Tk が2度目のクリック（ダブルクリック）と数えた
                self.leave_title()
            return None
        if row == 1:
            self.enter_title(self._col_at(event))
            self._drag = True
            return 'break'
        self.leave_title()
        # 目次・下の線の行を押した: ボタンを離すまでの動きで選択を広げない（このクリックは Text の束縛へ渡していないので、
        # そのまま流すと Tk が前の選択の起点から広げた・2026-11-15 うにさん「目次の行をクリックしてジャンプした後、
        # マウスを少し動かすと広い範囲が選択される」）。CN_TOC_CLICK_HOLD=0 で前の動き
        self._head_press = os.environ.get('CN_TOC_CLICK_HOLD') != '0'
        rows = getattr(editor, '_cn_head_rows', [])
        k = row - 2
        if 0 <= k < len(rows):
            self.jump(rows[k])
        return 'break'

    def _double(self, event):
        if header_row(self.app.editor, event.x, event.y) != 1:
            return self._click(event)
        self.enter_title(self._col_at(event))
        self.title.tag_add('sel', 'insert wordstart', 'insert wordend')
        self.title.mark_set('insert', 'insert wordend')
        self._show_caret()
        return 'break'

    def _triple(self, event):
        if header_row(self.app.editor, event.x, event.y) != 1:
            return self._click(event)
        self.enter_title(self._col_at(event))
        self.title.tag_add('sel', '1.0', '1.end')
        self.title.mark_set('insert', '1.end')
        self._show_caret()
        return 'break'

    def _shift_click(self, event):
        if not self._active or header_row(self.app.editor, event.x, event.y) != 1:
            return self._click(event)
        col = self._col_at(event)
        anchor = self.title.index('tk::anchor' + str(self.title))
        self.title.tag_remove('sel', '1.0', 'end')
        a, b = sorted((int(anchor.split('.')[1]), col))
        self.title.tag_add('sel', '1.%d' % a, '1.%d' % b)
        self.title.mark_set('insert', '1.%d' % col)
        self._show_caret()
        return 'break'

    def _b1_motion(self, event):
        if getattr(self, '_head_press', False):
            return 'break'
        if not (self._active and self._drag):
            return None
        col = self._col_at(event)
        if col is None:
            return 'break'
        try:
            anchor = int(str(self.title.index('tk::anchor' + str(self.title))).split('.')[1])
        except (tk.TclError, ValueError, IndexError):
            anchor = col
        self.title.tag_remove('sel', '1.0', 'end')
        a, b = sorted((anchor, col))
        if a != b:
            self.title.tag_add('sel', '1.%d' % a, '1.%d' % b)
        self.title.mark_set('insert', '1.%d' % col)
        self._show_caret()
        return 'break'

    def _release(self, event):
        if getattr(self, '_head_press', False):
            self._head_press = False
            return 'break'
        if self._drag:
            self._drag = False
            return 'break'
        return None

    def _motion(self, event):
        editor = self.app.editor
        row = header_row(editor, event.x, event.y)
        want = 'hand2' if row is not None and 2 <= row < 2 + len(getattr(editor, '_cn_head_rows', [])) else None
        if want != getattr(self, '_cursor_set', None):
            try:
                if want:
                    self._cursor_was = editor.cget('cursor')
                    editor.configure(cursor=want)
                else:
                    editor.configure(cursor=getattr(self, '_cursor_was', 'xterm'))
            except tk.TclError:
                pass
            self._cursor_set = want
        return None


def install(app):
    try:
        toc = InlineTitleToc(app)
        return toc
    except Exception:
        import traceback
        traceback.print_exc()
        return None
