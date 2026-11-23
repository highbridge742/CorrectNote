# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""本文の欄の長押しで語を選ぶ・選んだ範囲をドラッグで移す（2026-11-18 うにさん）。

「単語をクリックし続けたら、そこをダブルクリックした時と同じように範囲選択する。押し続けているときにマウスが
動いたら無効。範囲選択した範囲をクリックしなおしてドラッグして、別の場所にドロップしたら文字を移動させる。
範囲選択の端のほうはクリックしても動かないよう無効にする。ドラッグ中は、範囲をコピーと同じように白い枠で包む。
Ctrlを押しながらドロップしたら複製する。」

・長押し: LONGPRESS_MS（既定 220ms・上限 1000ms・デバッグのパラメータ）押したまま MOVE_PX より動かなければ、
  ダブルクリックと同じ手続き（mouse_words._double・形態素の区切りで語だけ）で語を選ぶ。その間に動いたら長押しは
  無効で、今までのドラッグ選択。ドラッグ中のカーソルは、カーソルを動かした時の色（editor_guides.FLASH_COLOR）で
  点滅させない。
・選んだ範囲の中で押して MOVE_PX より動かすと移動のドラッグ。範囲の最初の字と最後の字の上で押した時は、今までの
  クリック（選び直し・端の調整）。範囲の中で押して動かさずに離したら、今までどおりそこへカーソル。
・ドラッグ中は範囲をコピーの時と同じ白い枠で包み、落とす先にカーソルを出す。範囲の中・タイトルの行へは落とさない
  （取りやめ）。Esc で取りやめ。Ctrl を押したまま落とすと複製（元は残す）。移動・複製は Undo 1回で戻る。
・本文の欄だけ（補正欄・タイトルの行からは始めない）。自分の窓の中だけ（外の窓とはやり取りしない）。
CN_LONGPRESS_SELECT=0 で長押しを、CN_DRAG_MOVE=0 で移動を、前の形（無し）に戻す。
"""
import os
from types import SimpleNamespace as NS

TAG = 'CnDragMove'
LONGPRESS_MS = 220          # 2026-11-18 うにさん「長押しの時間はデフォルト220で、上限は1000まで」（初めは 500）
LONGPRESS_MS_MAX = 1000
MOVE_PX = 4
# 範囲の端で押した時は今までのクリック（選び直し・端の調整）。その端の幅（px・上限。字の幅の 1/4 より広くはしない）。
# 2026-11-20 うにさんの報告（2文字の語を掴めない）から。デバッグのパラメータ（drag_edge）
EDGE_PX = 3
EDGE_PX_MAX = 12
_DROP_MARK = 'cn_drag_drop'
# ドラッグで移す間、欄の上端・下端の帯に来たらその向きへ送り続ける（2026-11-20 うにさん「ドラッグ移動で、上下スクロールの
# 端までカーソルが来たらスクロールさせる」）。帯の幅（px・0 は1行の高さ）と送る間隔（ms）。デバッグのパラメータ
AUTOSCROLL_BAND_PX = 0
AUTOSCROLL_BAND_PX_MAX = 120
AUTOSCROLL_MS = 50
AUTOSCROLL_MS_MAX = 500


def autoscroll_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_DRAG_AUTOSCROLL') != '0'


def longpress_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_LONGPRESS_SELECT') != '0'


def drag_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_DRAG_MOVE') != '0'


_KEEP = object()


class DragMove:
    def __init__(self, app, widget, on_change=_KEEP, body=True):
        self.app = app
        self.w = widget
        # body: 本文の欄（タイトル・見出しの決まりを見る）。簡易入力の欄は False（2026-11-20 うにさん「簡易入力でも、
        # 長押し選択とドラッグ移動ができるようにする」）。on_change: 落とした後に呼ぶ（既定は app._on_change＝本文の
        # 解き直し。簡易入力は自分の <<Modified>> で気づくので None）
        self.body = body
        self.on_change = getattr(app, '_on_change', None) if on_change is _KEEP else on_change
        self.timer = None
        self.state = None            # None / 'armed' / 'dragging'
        self.start = None
        self.sel = None
        self.saved_insert = None
        self.fired = False
        self.scroll_job = None
        self.scroll_at = None           # 送り続ける間の指の位置（欄の中の x, y）
        widget.bind_class(TAG, '<ButtonPress-1>', self.press)
        widget.bind_class(TAG, '<B1-Motion>', self.motion)
        widget.bind_class(TAG, '<ButtonRelease-1>', self.release)
        widget.bind_class(TAG, '<Escape>', self.escape)
        tags = list(widget.bindtags())
        if TAG not in tags:
            # 本文の中のタイトルの束縛（いちばん前）のすぐ後ろ・欄そのものと Text の束縛より前
            at = 1 if tags and tags[0] == 'CorrectNoteHead' else 0      # title_inline.BIND_TAG
            tags.insert(at, TAG)
            widget.bindtags(tuple(tags))

    # 位置 ---------------------------------------------------------------------
    def _index(self, x, y):
        return str(self.w.index('@%d,%d' % (x, y)))

    def _in_header(self, x, y):
        raw = getattr(self.w, '_cn_body_raw', None)
        if not raw:
            return False
        try:
            import title_inline
            row = int(str(self.w.tk.call(raw, 'index', '@%d,%d' % (x, y))).split('.')[0])
            return row <= title_inline.head_rows(self.w)
        except Exception:
            return False

    def _title_has_cursor(self):
        if not self.body:
            return False
        toc = getattr(self.app, '_title_toc', None)
        try:
            return bool(toc is not None and getattr(toc, 'inline', False) and toc.has_cursor())
        except Exception:
            return False

    def _cmp(self, a, op, b):
        return bool(self.w.compare(a, op, b))

    def _inside_narrow(self, first, last, x, y):
        """狭い範囲（全角1字の幅より狭い・1行の中）は、全角1字の幅になるまで左右へ広げた所を「範囲の上」とみなす
        （2026-11-23 うにさん「半角1文字をドラッグ移動しにくい。クリックできる範囲を調整する」: 半角1字は 7px ほどで、
        端の 1px ずつを除くと掴める所が 5px しかなかった）。広げるのは足りない幅の分だけで、ふつうのクリックを奪いすぎない。"""
        w = self.w
        if str(w.index(first)).split('.')[0] != str(w.index('%s -1c' % last)).split('.')[0]:
            return False
        a, z = w.bbox(first), w.bbox('%s -1c' % last)
        if not a or not z:
            return False
        x0, x1 = a[0], z[0] + z[2]
        if not (a[1] <= y < a[1] + a[3]):
            return False
        try:
            import tkinter.font as tkfont
            full = tkfont.Font(font=w.cget('font')).measure('　')
        except Exception:
            full = 0
        width = x1 - x0
        if width <= 0 or width >= full:
            return False
        pad = (full - width) / 2.0
        return x0 - pad <= x < x1 + pad

    def _inside_core(self, idx, first, last, x=None, y=None):
        """範囲の中で、端の数 px を除いた所か（端は今までのクリック）。
        2026-11-20 うにさん「2文字の単語だったが、移動できなかった」: 前は最初の字と最後の字を丸ごと端にしていたので、
        1字・2字の範囲は掴める所が無かった。端は範囲の始まり・終わりの線から EDGE_PX（字の幅の 1/4 より狭くは
        しない上限）だけにする。CN_DRAG_EDGE_PX=0 で前の形（最初と最後の字は端）"""
        try:
            if x is not None and grab_min_on() and self._inside_narrow(first, last, x, y):
                return True
            if os.environ.get('CN_DRAG_EDGE_PX') == '0' or x is None:
                return (self._cmp(idx, '>=', '%s +1c' % first) and self._cmp(idx, '<', '%s -1c' % last))
            if not (self._cmp(idx, '>=', first) and self._cmp(idx, '<', last)):
                return False
            w = self.w
            for at, side in ((first, 'start'), ('%s -1c' % last, 'end')):
                box = w.bbox(at)
                if not box:
                    continue
                bx, by, bw, bh = box
                if not (by <= y < by + bh):
                    continue
                edge = min(EDGE_PX, max(1, bw // 4))
                if side == 'start' and x < bx + edge:
                    return False
                if side == 'end' and x >= bx + bw - edge:
                    return False
            return True
        except Exception:
            return False

    # 長押し -------------------------------------------------------------------
    def _cancel_timer(self):
        if self.timer is not None:
            try:
                self.w.after_cancel(self.timer)
            except Exception:
                pass
            self.timer = None

    def _fire(self, x, y):
        self.timer = None
        if self.state is not None or self._title_has_cursor():
            return
        w = self.w
        try:
            # ダブルクリックと同じ手続き（mouse_words._double: 形態素の区切りで語だけ。そのまま動かすと語の単位で広げる）。
            # 初めは Tk の語（text.tcl の selectMode word）を使い、空白の無い日本語の行は行の全部が選ばれた
            # （2026-11-18 うにさん「長押しで、今は行全体が選択されています」）
            import mouse_words
            from types import SimpleNamespace
            if mouse_words._double(self.app, SimpleNamespace(widget=w, x=x, y=y)) == 'break':
                self.fired = True
        except Exception:
            pass

    def _by_touch(self):
        """いまの押しが指から来たか（paper_window が窓の知らせで覚えた印）。指の押しは長押しの語選び・範囲の掴みに
        入れず、今までどおり（タップはカーソル・なぞりはスクロール）。2026-11-20 うにさん「タッチモニター1本指で
        スクロールにならない」。CN_TOUCH_NO_DRAG=0 で前の形"""
        try:
            import paper_window
            return paper_window.press_is_touch(self.w)
        except Exception:
            return False

    # 束縛 ---------------------------------------------------------------------
    def press(self, e):
        self._cancel_timer()
        self.state = None
        self.fired = False
        self.start = (e.x, e.y)
        if self._title_has_cursor() or self._in_header(e.x, e.y) or (e.state & 0x0001):
            return None
        if self._by_touch():
            return None
        w = self.w
        try:
            ranges = w.tag_ranges('sel')
        except Exception:
            ranges = ()
        if ranges and drag_on():
            first, last = str(ranges[0]), str(ranges[-1])
            idx = self._index(e.x, e.y)
            if self._inside_core(idx, first, last, e.x, e.y):
                self.state = 'armed'
                self.sel = (first, last)
                self.saved_insert = str(w.index('insert'))
                try:
                    w.focus_set()
                except Exception:
                    pass
                return 'break'
        if longpress_on():
            self.timer = w.after(LONGPRESS_MS, lambda x=e.x, y=e.y: self._fire(x, y))
        return None

    def _moved(self, e):
        if self.start is None:
            return False
        return abs(e.x - self.start[0]) > MOVE_PX or abs(e.y - self.start[1]) > MOVE_PX

    def motion(self, e):
        if self.timer is not None and self._moved(e):
            self._cancel_timer()            # 押している間に動いた: 長押しは無効（今までのドラッグ選択）
        if self.state == 'armed' and self._moved(e):
            self.state = 'dragging'
            self._caret_on()
            try:
                self.app._show_copy_frame(self.w, self.sel[0], self.sel[1])
            except Exception:
                pass
        if self.state == 'dragging':
            if not self._in_band(e.x, e.y) and self._outside(e):     # 欄の中の上下の帯にいる間は外へ出たとみなさない
                return self._drag_out(e)
            try:
                self.w.mark_set('insert', '@%d,%d' % (e.x, e.y))     # 落とす先のカーソル
            except Exception:
                pass
            self._autoscroll(e)
            return 'break'
        if self.state == 'armed':
            return 'break'
        return None

    # 端で送り続ける（autoscroll）----------------------------------------------------
    def _band(self):
        try:
            band = int(AUTOSCROLL_BAND_PX)
        except (TypeError, ValueError):
            band = 0
        if band > 0:
            return band
        try:
            import tkinter.font as tkfont
            return max(8, int(tkfont.Font(font=self.w.cget('font')).metrics('linespace')))
        except Exception:
            return 20

    def _edge_zone(self, y):
        """欄の上端・下端の帯なら (向き, 深さ 0〜1)。帯の外なら None。欄の外（上・下）も帯の一番奥とみなす。"""
        if not autoscroll_on():
            return None
        try:
            h = int(self.w.winfo_height())
        except Exception:
            return None
        band = min(self._band(), max(1, h // 3))
        if y < band:
            return -1, min(1.0, (band - y) / float(band))
        if y >= h - band:
            return 1, min(1.0, (y - (h - band) + 1) / float(band))
        return None

    def _in_band(self, x, y):
        """欄の中（横も）で、上下の帯にいるか。横へ出た時は外へのドロップ（drag_out）のまま。"""
        try:
            w, h = int(self.w.winfo_width()), int(self.w.winfo_height())
        except Exception:
            return False
        return 0 <= x < w and 0 <= y < h and self._edge_zone(y) is not None

    def _autoscroll(self, e):
        if getattr(self.app, '_overview', None) is not None:      # 俯瞰の間はしない
            self._stop_scroll()
            return
        if self._edge_zone(e.y) is None:
            self._stop_scroll()
            return
        self.scroll_at = (e.x, e.y)
        if self.scroll_job is None:
            self._scroll_tick()

    def _scroll_tick(self):
        self.scroll_job = None
        if self.state != 'dragging' or self.scroll_at is None:
            return
        x, y = self.scroll_at
        zone = self._edge_zone(y)
        if zone is None or getattr(self.app, '_overview', None) is not None:
            return
        direction, depth = zone
        lines = 1 + int(depth * 2.999)            # 端に近いほど速く（1〜3行）
        try:
            self.w.yview_scroll(direction * lines, 'units')
            h = int(self.w.winfo_height())
            self.w.mark_set('insert', '@%d,%d' % (x, max(0, min(h - 1, y))))     # 落とす先のカーソルも付いていく
        except Exception:
            return
        try:
            self.scroll_job = self.w.after(max(10, int(AUTOSCROLL_MS)), self._scroll_tick)
        except Exception:
            self.scroll_job = None

    def _stop_scroll(self):
        job, self.scroll_job = self.scroll_job, None
        self.scroll_at = None
        if job is not None:
            try:
                self.w.after_cancel(job)
            except Exception:
                pass

    def _caret_on(self):
        """落とす先のカーソルを、カーソルを動かした時と同じ色にして、点滅させない（2026-11-18 うにさん「ドラッグ移動中の
        カーソルは、カーソル移動させた時と同じように色を付ける。動かしたときに点滅して見えないことがないようにする」）。"""
        try:
            import editor_guides
            color = editor_guides.FLASH_COLOR
        except Exception:
            color = '#ee963e'
        w = self.w
        try:
            self.caret = (str(w.cget('insertbackground')), int(w.cget('insertofftime')), color)
            w.configure(insertbackground=color, insertofftime=0)
        except Exception:
            self.caret = None

    def _caret_off(self):
        caret, self.caret = getattr(self, 'caret', None), None
        if caret is None:
            return
        background, off, color = caret
        w = self.w
        try:
            # 間にほかの所（editor_guides の光り）が色を替えていたら、そちらに任せる
            if str(w.cget('insertbackground')) == color and background != color:
                w.configure(insertbackground=background)
            if int(w.cget('insertofftime')) == 0 and off:
                w.configure(insertofftime=off)
        except Exception:
            pass

    # 窓の外へ（drag_out・2026-11-20 うにさん「アプリ外の入力欄にドロップできるようにする。この場合は複製として元の
    # 文字を残す」）---------------------------------------------------------------
    def _window_rect(self):
        top = self.w.winfo_toplevel()
        x, y = top.winfo_rootx(), top.winfo_rooty()
        return (x, y, x + top.winfo_width(), y + top.winfo_height())

    def _outside(self, e):
        xr, yr = getattr(e, 'x_root', None), getattr(e, 'y_root', None)
        if xr is None or yr is None:
            return False
        try:
            import drag_out
            if not drag_out.enabled():
                return False
            x0, y0, x1, y1 = self._window_rect()
        except Exception:
            return False
        return not (x0 <= xr < x1 and y0 <= yr < y1)

    @staticmethod
    def _left_down():
        try:
            import ctypes
            user32 = ctypes.windll.user32
            vk = 0x02 if user32.GetSystemMetrics(23) else 0x01
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            return True

    def _drag_out(self, e, run=None):
        """外の窓へ OLE のドラッグで渡す（複製・元の字は残す）。窓の中へ戻ったら、アプリの中の移動の続き。"""
        import drag_out
        first, last = self.sel
        try:
            text = self.w.get(first, last)
            rect = self._window_rect()
        except Exception:
            return 'break'
        inside = lambda x, y: rect[0] <= x < rect[2] and rect[1] <= y < rect[3]
        try:
            result = (run or drag_out.drag_text_out)(text, inside)
        except Exception:
            result = 'cancelled'
        self.out_result = result
        if result == 'back':
            # 窓の中へ戻った: 移動のドラッグを続ける。左をもう離していたら（離しの知らせは OLE が受けた）、指の所へ落とす
            if not self._left_down():
                try:
                    px = self.w.winfo_pointerx() - self.w.winfo_rootx()
                    py = self.w.winfo_pointery() - self.w.winfo_rooty()
                except Exception:
                    px, py = e.x, e.y
                return self.release(NS(x=px, y=py, state=getattr(e, 'state', 0)))
            return 'break'
        self.state = None
        self._end_frame()
        try:
            if self.saved_insert:
                self.w.mark_set('insert', self.saved_insert)
            # OLE のドラッグが左の離しを受けたので、Tk の押したままの印を下ろす（次の動きがドラッグ選択にならないように）
            self.w.event_generate('<ButtonRelease-1>', x=e.x, y=e.y)
        except Exception:
            pass
        return 'break'

    def _end_frame(self):
        self._stop_scroll()
        self._caret_off()
        try:
            self.app._clear_copy_emphasis()
        except Exception:
            pass

    def release(self, e):
        self._cancel_timer()
        state, self.state = self.state, None
        if self.fired:
            self.fired = False
        if state == 'armed':
            # 範囲の中で押して動かさずに離した: 今までどおりそこへカーソル
            try:
                self.w.tag_remove('sel', '1.0', 'end')
                self.w.mark_set('insert', '@%d,%d' % (e.x, e.y))
            except Exception:
                pass
            return 'break'
        if state != 'dragging':
            return None
        self._end_frame()
        copy = bool(e.state & 0x0004)
        self.drop(self._index(e.x, e.y), copy, header=self._in_header(e.x, e.y))
        return 'break'

    def escape(self, e):
        if self.state != 'dragging':
            return None
        self.state = None
        self._end_frame()
        try:
            if self.saved_insert:
                self.w.mark_set('insert', self.saved_insert)
        except Exception:
            pass
        return 'break'

    # 落とす -------------------------------------------------------------------
    def drop(self, at, copy=False, header=False):
        """範囲 self.sel を at へ移す（copy なら複製）。範囲の中・見出しへは落とさない。戻り値: 動かしたか。"""
        w = self.w
        first, last = self.sel
        if header or (self._cmp(at, '>', first) and self._cmp(at, '<', last)) or (
                not copy and (self._cmp(at, '==', first) or self._cmp(at, '==', last))):
            try:
                if self.saved_insert:
                    w.mark_set('insert', self.saved_insert)
            except Exception:
                pass
            return False
        from text_edit import undo_group
        rows = None
        if line_move_on():
            try:
                rows = _rows_of_line_selection(w, first, last)
                if rows is not None and str(w.index(at)) != str(w.index('%s linestart' % at)):
                    rows = None                         # 行の途中へ落とす時は今までどおり
            except Exception:
                rows = None
        if rows is not None:
            return self._drop_lines(rows, at, copy)
        try:
            text = w.get(first, last)
            if not text:
                return False
            w.mark_set(_DROP_MARK, at)
            w.mark_gravity(_DROP_MARK, 'left')
            with undo_group(w):
                if not copy:
                    w.delete(first, last)
                w.insert(_DROP_MARK, text)
            start = str(w.index(_DROP_MARK))
            end = str(w.index('%s +%dc' % (_DROP_MARK, len(text))))
            w.mark_unset(_DROP_MARK)
            w.tag_remove('sel', '1.0', 'end')
            if not deselect_on():
                w.tag_add('sel', start, end)
            w.mark_set('insert', end)
        except Exception:
            return False
        on_change = self.on_change
        if on_change is not None:
            try:
                on_change()             # 落とした所・抜いた所は補正の解き直しの対象
            except Exception:
                pass
        return True

    def _drop_lines(self, rows, at, copy):
        """行で選んだ行 rows（lo, hi）を、行頭 at へ行として移す（copy なら複製）。元の場所は後ろの改行ごと消して空行を
        残さない（最終行は前の改行を消す）。落とした行頭には「行＋改行」を入れる。Undo 1回で戻る
        （2026-11-23 うにさん「行番号をクリックして、またはShift+スペースで行を選択した場合、その範囲をドラッグ移動して
        行頭に持って行った場合は後ろの改行も移動する。移す前の場所に空白行は残らず、移したあとは後ろに改行を加える」）。"""
        from text_edit import undo_group
        w = self.w
        lo, hi = rows
        try:
            last_row = int(str(w.index('end-1c')).split('.')[0])
            target = int(str(w.index(at)).split('.')[0])
            if not copy and lo <= target <= hi + 1:
                # 自分の行の中・すぐ下の行頭（同じ所）へは落とさない
                if self.saved_insert:
                    w.mark_set('insert', self.saved_insert)
                return False
            text = w.get('%d.0' % lo, '%d.end' % hi)
            w.mark_set(_DROP_MARK, '%d.0' % target)
            w.mark_gravity(_DROP_MARK, 'left')
            with undo_group(w):
                if not copy:
                    if hi < last_row:
                        w.delete('%d.0' % lo, '%d.0' % (hi + 1))
                    elif lo > 1:
                        w.delete('%d.end' % (lo - 1), '%d.end' % hi)
                    else:
                        w.delete('%d.0' % lo, '%d.end' % hi)
                w.insert(_DROP_MARK, text + chr(10))
            start = str(w.index(_DROP_MARK))
            end = str(w.index('%s +%dc' % (_DROP_MARK, len(text) + 1)))
            w.mark_unset(_DROP_MARK)
            w.tag_remove('sel', '1.0', 'end')
            if not deselect_on():
                w.tag_add('sel', start, end)
                mark_lines(w)                               # 続けて行として移せる
            else:
                w._cn_line_sel = None
            w.mark_set('insert', end)                       # 移した行の次の行頭
        except Exception:
            return False
        on_change = self.on_change
        if on_change is not None:
            try:
                on_change()
            except Exception:
                pass
        return True


def grab_min_on(environ=None):
    """狭い選択（半角1字など）を掴める幅を全角1字ぶんまで広げる（CN_DRAG_GRAB_MIN_WIDTH=0 で前の形）。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_DRAG_GRAB_MIN_WIDTH') != '0'


def deselect_on(environ=None):
    """ドラッグで移した・複製した後は選択を外す（カーソルは落とした範囲の終わり。2026-11-23 うにさん「ドラッグ移動で
    運んだあとは、選択範囲解除する」）。CN_DRAG_DROP_DESELECT=0 で前の形（落とした範囲を選んだまま）。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_DRAG_DROP_DESELECT') != '0'


def line_move_on(environ=None):
    """行で選んだ範囲を行頭へ落とした時は行として移す（2026-11-23 うにさん）。CN_LINE_DRAG_MOVE=0 で前の形。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_LINE_DRAG_MOVE') != '0'


def mark_lines(widget):
    """いまの選択は行で選んだもの（行番号のクリック・ドラッグ・Shift+Space）と覚える。覚えるのは行（両端含む）。
    選択が手で変わって、行まるごとでない・行が違う時は、行として扱わない（drop で比べる）。
    行番号のクリックは、選んだ直後に選択の終わりが「次の行頭」から「その行の終わり」へ作り直される（離した時）ので、
    範囲の字の位置ではなく行で比べる（2026-11-23 うにさん「Shift+スペースではできたが、行番号クリックではできなかった」）。"""
    try:
        ranges = widget.tag_ranges('sel')
        widget._cn_line_sel = _whole_rows(widget, ranges[0], ranges[1]) if len(ranges) == 2 else None
    except Exception:
        widget._cn_line_sel = None


def _whole_rows(w, first, last):
    """[first, last) が行まるごと（行頭〜次の行頭・行頭〜行の終わり）なら (lo, hi)。でなければ None。"""
    lo = int(str(w.index(first)).split('.')[0])
    if str(w.index(first)) != '%d.0' % lo:
        return None
    end_row, end_col = (int(p) for p in str(w.index(last)).split('.'))
    if end_col == 0 and end_row > lo:
        return lo, end_row - 1
    if str(w.index(last)) == str(w.index('%d.0 lineend' % end_row)):
        return lo, end_row
    return None


def _rows_of_line_selection(w, first, last):
    """(lo, hi)：行で選んだ範囲の行（両端含む）。行で選んだ範囲でなければ None。"""
    rows = _whole_rows(w, first, last)
    if rows is None or getattr(w, '_cn_line_sel', None) != rows:
        return None
    return rows


def quick_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_QUICK_DRAG') != '0'


def install(app, widget, on_change=_KEEP, body=True):
    if getattr(widget, '_cn_drag_move', None) is not None:
        return widget._cn_drag_move
    try:
        widget._cn_drag_move = DragMove(app, widget, on_change=on_change, body=body)
    except Exception:
        widget._cn_drag_move = None
    return widget._cn_drag_move
