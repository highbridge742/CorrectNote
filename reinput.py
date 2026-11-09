# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""再入力変換（うにさん・2026-11-02）。確定した語を読みに開いて、打ち直さずに変換し直す。

メモ欄で Ctrl だけを 0.4 秒以内に2回押して離すと、カーソルの語（Ctrl+左右の止まる位置の間）を平仮名に
開き、薄い色の範囲にする。範囲がある間:
    スペース   範囲全体を変換し、先頭の候補を入れる。続けて押すと次の候補
    Enter      今の形で確定
    Esc        開く前の字に戻す
    範囲の外へカーソルを出す（左右キー・PgUp・クリックなど）
        字を変えていない → Esc と同じく元に戻す ／ 字を変えた → スペースと同じく変換して終える
        ／ 候補を選んでいる途中 → 今の候補で確定
IME の変換中（未確定の字がある間）のキーは IME に任せる。範囲の中で字を足し引きしても mark が追う。
全体のフックは使わない（アプリの窓の中のキーだけ）。書き換え全部で Undo 1回。読みの台帳には書かない。
"""
import time

TAG = 'cn_reinput'
START = 'cn_reinput_start'
END = 'cn_reinput_end'
HERE = 'cn_reinput_cursor'
BIND_TAG = 'CorrectNoteReInput'
LIST_TAG = 'CorrectNoteReInputList'
# Ctrl の2回押し: 1回の押している長さと、離してから次に押すまで（2026-11-03 うにさん「反応しない時がある」。
# 前は1回目を押してから2回目を離すまでの全部で 0.4 秒で、0.1＋0.25＋0.1 の普通の速さが外れていた）
TAP_HOLD_MS = 400
TAP_GAP_MS = 400
SAME_SPACE_S = 0.5
TYPED_WAIT_MS = 50
TYPED_WAIT_TRIES = 30       # 打った行の答えを待つのは 1.5 秒まで
_CONTROL = ('Control_L', 'Control_R')
_MODIFIERS = _CONTROL + ('Shift_L', 'Shift_R', 'Alt_L', 'Alt_R')
_RETURN = ('Return', 'KP_Enter')
_SPACES = (' ', '　')
KINDS = ('homophone', 'kanji', 'kana')     # 読みが同じ候補だけ（打ち間違いの候補は出さない）
HINT = '再入力変換: スペースで変換・Enterで確定・Escで元に戻す'


def _is_kana(ch):
    return 'ぁ' <= ch <= 'ヿ'


def _hiragana(text):
    from kana_text import katakana_to_hiragana
    return katakana_to_hiragana(text)


def _reads_as_kana(text):
    return bool(text) and all('ぁ' <= ch <= 'ゟ' or ch == 'ー' for ch in text)


def _split_ascii(text):
    """[(英数字か, 字の並び)]。英字はそのまま残す。"""
    parts = []
    for ch in text:
        flag = ch.isascii() and not ch.isspace()
        if parts and parts[-1][0] == flag:
            parts[-1][1] += ch
        else:
            parts.append([flag, ch])
    return parts


def _is_kanji(ch):
    return '\u4e00' <= ch <= '\u9fff' or ch == '々'


_VOICED = dict(zip('かきくけこさしすせそたちつてとはひふへほ', 'がぎぐげござじずぜぞだぢづでどばびぶべぼ'))
_PLOSIVE = dict(zip('かきくけこさしすせそたちつてとはひふへほ', 'かきくけこさしすせそたちつてとぱぴぷぺぽ'))


NOT_AT_HEAD = 'っんゃゅょぁぃぅぇぉゎー'


def _sound_forms(reading):
    """連濁・半濁音・促音便も同じ字の読みと見る（学校→がっこう・発表→はっぴょう）。"""
    out = {reading}
    head = reading[:1]
    for table in (_VOICED, _PLOSIVE):
        if head in table:
            out.add(table[head] + reading[1:])
    for form in list(out):
        if len(form) >= 2 and form[-1] in 'くきつち':
            out.add(form[:-1] + 'っ')
    return out


def _split_run(run, reading, char_readings):
    """漢字の並びの読みを字ごとに分けた長さの並び。分けられなければ None。同じ分け方が2通りあれば採らない。"""
    forms = [set().union(*(_sound_forms(r) for r in char_readings(ch))) if char_readings(ch) else set() for ch in run]
    found = []
    def walk(i, at, lengths):
        if len(found) > 1:
            return
        if i == len(run):
            if at == len(reading):
                found.append(tuple(lengths))
            return
        for form in forms[i]:
            if form and reading.startswith(form, at):
                walk(i + 1, at + len(form), lengths + [len(form)])
    walk(0, 0, [])
    if found:
        return found[0] if len(found) == 1 else None
    # 1字だけ読みの候補に無いなら（表が訓読みしか持たない字）、残りをその字の読みと見る。字の頭に立たないかなは除く
    def guess(i, at, lengths, used):
        if i == len(run):
            if at == len(reading) and used:
                found.append(tuple(lengths))
            return
        for form in forms[i]:
            if form and reading.startswith(form, at):
                guess(i + 1, at + len(form), lengths + [len(form)], used)
        if not used and at < len(reading) and reading[at] not in NOT_AT_HEAD:
            for size in range(1, len(reading) - at + 1):
                guess(i + 1, at + size, lengths + [size], True)
    guess(0, 0, [], False)
    found = list(dict.fromkeys(found))
    return found[0] if len(found) == 1 else None


def cut_column(original, reading, at, char_readings=lambda ch: ()):
    """caret_column と同じ対応で、字の間が決まらなければ None（語の読みを字の位置で切り出す時）。"""
    return caret_column(original, reading, at, char_readings, strict=True)


def caret_column(original, reading, at, char_readings=lambda ch: (), strict=False):
    """original の at 字目の間に対応する、reading の中の位置。漢字1字が複数のかなに開く所は字ごとの読みで
    分け、分けられなければその漢字の並びのかなの後ろ。全体が対応しなければ reading の終わり。"""
    import re
    if at <= 0:
        return 0
    if at >= len(original):
        return len(reading)
    parts = re.findall('[\u4e00-\u9fff々]+|[^\u4e00-\u9fff々]+', original)
    pattern = ''.join('(.+?)' if _is_kanji(part[0]) else re.escape(_hiragana(part)) for part in parts)
    match = re.fullmatch(pattern, reading, re.S)
    if match is None:
        return None if strict else len(reading)
    at_original = group = 0
    for part in parts:
        end = at_original + len(part)
        if _is_kanji(part[0]):
            group += 1
            first, last = match.start(group), match.end(group)
            if at <= end:
                lengths = _split_run(part, reading[first:last], char_readings)
                if at == at_original:
                    return first
                if at == end:
                    return last
                if lengths is None:
                    return None if strict else last
                return first + sum(lengths[:at - at_original])
            done = last
        else:
            first = done if at_original else 0
            if at <= end:
                return first + at - at_original
            done = first + len(part)
        at_original = end
    return len(reading)


def _key_ms(event):
    """そのキーが押された時刻（ミリ秒）。Tk の event.time は Tk が処理した時刻なので（この PC で確かめた: 0.5秒空けて
    送った2つが同じ時刻になる）、本体が忙しいと間が伸び縮みする。Windows のメッセージの時刻を使う。"""
    import tkinter
    if isinstance(event, tkinter.Event) and getattr(event, 'time', 0):
        try:
            import ctypes
            return ctypes.windll.user32.GetMessageTime() & 0xFFFFFFFF
        except (AttributeError, OSError):
            return event.time & 0xFFFFFFFF
    got = getattr(event, 'time', None)
    return got & 0xFFFFFFFF if isinstance(got, int) and got else int(time.monotonic() * 1000) & 0xFFFFFFFF


def _since(later, earlier):
    return (later - earlier) & 0xFFFFFFFF      # 49日で一周する


def _no_key(event):
    """IME が受け取ったキー（Windows の VK_PROCESSKEY）。何のキーかは分からない。Ctrl がこの形で来ても数え直さない。"""
    return getattr(event, 'keycode', 0) == 229 or getattr(event, 'keysym', '') in ('??', '')


def _is_space(event):
    """半角・IME の全角のスペース。keysym が space でも IME が別の字にしたキー（映）は字。"""
    char = getattr(event, 'char', None)
    if char == '\u3000':
        return True
    return getattr(event, 'keysym', '') == 'space' and char in (None, ' ', '')


class CursorHider:
    """再変換・再入力変換のキー操作の間、アプリの欄の上のマウスカーソルを隠す（2026-11-03 うにさん）。
    欄の cursor を一時的に none にするだけで、Windows の設定には触らない。マウスを動かす・モードが終わる・
    タブを替える・焦点が外れる・閉じる で元のカーソル名に戻す。"""
    MOVE_PX = 1     # カーソルの付け替えや窓の出入りで来る「動いていない Motion」は数えない。動いたら距離によらず戻す
    WATCH_MS = 1000 # 隠している間の見張り: 欄の外で動いた・モードが終わったのを取りこぼしても戻す

    def __init__(self, app):
        self.app = app
        self.saved = {}
        self.at = None
        self._watch = None

    def _widgets(self):
        app = self.app
        return [w for w in (getattr(app, 'editor', None), getattr(app, 'result_view', None), getattr(app, '_quick_text', None)) if w is not None]

    def _hide_on(self, widget):
        try:
            if widget not in self.saved:
                from typing_pointer import shape_before_hiding
                self.saved[widget] = shape_before_hiding(widget)
                widget.configure(cursor='none')
        except Exception:
            self.saved.pop(widget, None)

    def hide(self, *more):
        """キー操作が入った。"""
        for widget in self._widgets() + list(more):
            self._hide_on(widget)
        if self.at is None and self.saved:
            try:
                first = next(iter(self.saved))
                self.at = first.winfo_pointerxy()
            except Exception:
                self.at = None
        self._start_watch()

    def _start_watch(self):
        if self._watch is None and self.saved:
            try:
                self._watch = next(iter(self.saved)).after(self.WATCH_MS, self._watching)
            except Exception:
                self.restore()

    def _watching(self):
        """隠したまま戻らない道を残さない（2026-11-03 うにさん「マウスカーソルが消えて戻らない」）。"""
        self._watch = None
        if not self.saved:
            return
        try:
            for widget in list(self.saved):
                if not widget.winfo_exists():
                    self.saved.pop(widget, None)
            first = next(iter(self.saved), None)
            here = first.winfo_pointerxy() if first is not None else None
        except Exception:
            self.restore()
            return
        if not self.saved or not self.mode_active() or (self.at is not None and here != tuple(self.at)):
            self.restore()
            return
        self._start_watch()

    def add(self, widget):
        """隠している間に出た候補一覧。"""
        if self.saved:
            self._hide_on(widget)

    def restore(self):
        saved, self.saved = self.saved, {}
        self.at = None
        watch, self._watch = self._watch, None
        if watch is not None:
            for widget in saved:
                try:
                    widget.after_cancel(watch)
                    break
                except Exception:
                    pass
        for widget, cursor in saved.items():
            try:
                widget.configure(cursor=cursor)
            except Exception:
                pass

    def mode_active(self):
        app = self.app
        if getattr(app, '_dropdown', None) is not None or getattr(app, '_f2_focus_target', None) is not None:
            return True
        return any(r is not None and r.state is not None for r in (getattr(app, '_reinput', None), getattr(app, '_quick_reinput', None)))

    def check(self):
        """モードが終わっていれば戻す。"""
        if self.saved and not self.mode_active():
            self.restore()

    def check_soon(self):
        if not self.saved:
            return
        widget = next(iter(self.saved))
        try:
            widget.after_idle(self.check)
        except Exception:
            self.restore()

    def on_motion(self, event=None):
        if not self.saved:
            return None
        at = (getattr(event, 'x_root', None), getattr(event, 'y_root', None))
        if self.at is None or None in at or abs(at[0] - self.at[0]) >= self.MOVE_PX or abs(at[1] - self.at[1]) >= self.MOVE_PX:
            self.restore()
        return None

    def on_enter(self, event=None):
        """欄へ入り直した: どのモードも開いていなければ戻す。"""
        self.check()
        return None

    def on_focus_out(self, event=None):
        """アプリの外へ焦点が行った時だけ（欄と候補一覧の間の行き来では戻さない）。"""
        if not self.saved:
            return None
        widget = next(iter(self.saved))
        def later():
            try:
                outside = widget.focus_get() is None
            except Exception:
                outside = True
            if outside:
                self.restore()
        try:
            widget.after_idle(later)
        except Exception:
            self.restore()
        return None


def hide_cursor_for_reconvert(app):
    """再変換（F5 等）を開いた時点で隠す。範囲も一覧も開かなかったら何もしない。"""
    hider = getattr(app, '_cursor_hider', None)
    if hider is None or (getattr(app, '_dropdown', None) is None and getattr(app, '_f2_focus_target', None) is None):
        return
    parts = getattr(app, '_dropdown_parts', None) if getattr(app, '_dropdown', None) is not None else None
    listbox = parts.get('lb') if isinstance(parts, dict) else None
    hider.hide(*((listbox,) if listbox is not None else ()))


def check_cursor(app):
    hider = getattr(app, '_cursor_hider', None)
    if hider is not None:
        hider.check_soon()


def restore_cursor(app):
    hider = getattr(app, '_cursor_hider', None)
    if hider is not None:
        hider.restore()


def _F5(widget):
    from types import SimpleNamespace
    return SimpleNamespace(widget=widget, keysym='F5', char='', state=0, keycode=116)


class ReInput:
    def __init__(self, app, widget, quick=False):
        self.app = app
        self.widget = widget
        self.quick = quick          # 簡易入力の欄（解析の控え・確定の読みは本体のものを使わない）
        self._waiting = None        # 打った範囲の答えを待っている間の印
        self.state = None
        self._down_at = None        # この Ctrl を押した時刻（押しっぱなしの繰り返しでは変えない）
        self._released_at = None    # 1回目の Ctrl を離した時刻
        self._chord = False         # Ctrl を押したまま別のキーを押した（Ctrl+C の形）
        self._space_at = 0.0        # スペースの押しを受けた時刻
        self._chosen = None         # 本人が変換で選んだ語 (その行の字, 語, 覚えた直し, 開く前の行の字)
        self._kept_choices = None   # 覚える前の選び直しの記憶（Undo で開く前に戻ったら戻す）

    # --- キーの入口 ---------------------------------------------------------
    def on_press(self, event):
        key = getattr(event, 'keysym', '')
        if key in _CONTROL:
            if self._down_at is None:
                self._down_at = _key_ms(event)
                self._chord = False
            return None
        self.other_key(event)
        self._waiting = None
        if key not in _MODIFIERS and (self.state is not None or self._reconvert_range_open()):
            hider = getattr(self.app, '_cursor_hider', None)
            if hider is not None:
                hider.hide()
        if self.state is None and _is_space(event) and self._reconvert_range_open():
            self.start()
            return 'break'
        if self.state is None and _is_space(event) and self._selection_space(event):
            self.start()
            return 'break'
        if self.state is None or self.composing():
            return None
        if _is_space(event):
            self._space_at = time.monotonic()
            self.convert_next()
            return 'break'
        if key in _RETURN:
            self.finish()
            return 'break'
        if key == 'Escape':
            self.cancel()
            return 'break'
        return None

    def _selection_space(self, event):
        """本文を1行の中で選んでいて、修飾キーなしのスペース（IME が字にしたキーは別）。"""
        if int(getattr(event, 'state', 0) or 0) & 0x5:
            return False
        if self.composing() or getattr(self.app, '_pick_mode', None) or getattr(self.app, '_dropdown', None) is not None:
            return False
        ranges = self.widget.tag_ranges('sel')
        return (len(ranges) == 2 and str(ranges[0]).split('.')[0] == str(ranges[1]).split('.')[0]
                and bool(self.widget.get(ranges[0], ranges[1]).strip()))

    def _reconvert_range_open(self):
        """再変換の範囲が残っている（候補が無くて一覧が閉じている語）。一覧が開いていればキーは一覧へ行く。"""
        target = getattr(self.app, '_f2_focus_target', None)
        return (isinstance(target, dict) and target.get('widget') is self.widget and not self.composing()
                and getattr(self.app, '_dropdown', None) is None)

    def on_release(self, event):
        key = getattr(event, 'keysym', '')
        if key in _CONTROL:
            self._control_released(event)
        # ほかのキーを離しただけでは数え直さない（打った字のキーを離すのが Ctrl の後になるのは普通のこと）。
        # 押した時に数え直している
        if self.state is not None and key not in _CONTROL:
            self.settle()
        return None

    def on_pointer(self, event=None):
        self._forget_taps()
        self._waiting = None
        return None

    def on_focus_out(self, event=None):
        self.on_pointer(event)
        hider = getattr(self.app, '_cursor_hider', None)
        if hider is not None:
            hider.on_focus_out(event)
        return None

    def on_pointer_release(self, event=None):
        self._forget_taps()
        if self.state is not None:
            self.settle()
        return None

    def _forget_taps(self):
        self._down_at = self._released_at = None

    def other_key(self, event):
        """Ctrl 以外のキーが押された。"""
        if _no_key(event):
            return
        # Ctrl+C の形: そのあと Ctrl を離しても、押しただけの1回に数えない
        if self._down_at is not None or int(getattr(event, 'state', 0) or 0) & 4:
            self._chord = True
        self._forget_taps()

    def _control_released(self, event):
        now = _key_ms(event)
        down, self._down_at = self._down_at, None
        chord, self._chord = self._chord, False
        if down is None:
            if chord:
                self._forget_taps()
                return
            down = now      # 押した報せが届いていない（IME が受け取った）
        if _since(now, down) > TAP_HOLD_MS:
            self._forget_taps()
            return
        first = self._released_at
        if first is not None and _since(down, first) <= TAP_GAP_MS:
            self._forget_taps()
            self.start()
            return
        self._released_at = now

    def composing(self):
        try:
            return bool(self.app._composing(self.widget))
        except Exception:
            return False

    # --- 範囲 ---------------------------------------------------------------
    def word_columns(self, row, text, column):
        """(始まり, 終わり) の字の位置。Ctrl+左右の止まる位置と同じ規則。語が無ければ None。"""
        if not text:
            return None
        edge = lambda at, direction: self.app._text_edge_column(self.widget, row, text, at, direction)
        if column >= len(text):
            start, end = edge(len(text), -1), len(text)
        elif column == 0 or edge(edge(column, 1), -1) == column:
            start, end = column, edge(column, 1)
        else:
            start, end = edge(column, -1), edge(column, 1)
        return (start, end) if 0 <= start < end else None

    def start(self):
        """Ctrl の2回押し。再変換で選んでいる範囲 → 今打って確定した範囲 → カーソルの語 の順。"""
        if self.state is not None:
            self.finish()
        app, w = self.app, self.widget
        self._waiting = None
        if self.composing() or getattr(app, '_pick_mode', None):
            return False
        chosen = self._selected_span()
        if chosen is not None:
            row, span, column = chosen
            return self._open_span(row, span, column)
        if getattr(app, '_dropdown', None) is not None:
            return False
        typed = self._typed_span()
        if typed is not None:
            self._waiting = typed
            self._act_on_typed(typed, 0)
            return True
        row = int(w.index('insert').split('.')[0])
        column = len(w.get(f'{row}.0', 'insert'))
        text = w.get(f'{row}.0', f'{row}.end')
        span = self.word_columns(row, text, column)
        return False if span is None else self._open_span(row, span, column)

    def _open_span(self, row, span, column):
        w = self.widget
        text = w.get(f'{row}.0', f'{row}.end')
        first, last = f'{row}.0+{span[0]}c', f'{row}.0+{span[1]}c'
        original = w.get(first, last)
        reading = self.reading_of(row, span[0], original)
        line_before = text
        w.tag_remove('sel', '1.0', 'end')
        w.mark_set(START, first); w.mark_gravity(START, 'left')
        w.mark_set(END, last); w.mark_gravity(END, 'right')
        self.state = dict(original=original, shown=original, reading=None, choices=None, at=-1, owner=self._owner(), wrote=False, line_before=line_before)
        self._color()
        self._write(reading)
        self.state.update(opened=self.current())
        self._place_caret(row, text, span, column, original, reading)
        self._say(HINT)
        hider = getattr(self.app, '_cursor_hider', None)
        if hider is not None:
            hider.hide()        # 始めた時点で（Ctrl 2回・Space・選択＋Space のどれでも）
        return True

    def _selected_span(self):
        """再変換（F5 等）で選んでいる範囲か、本文の選択（1行の中）。(行, (始まり, 終わり)) か None。"""
        app, w = self.app, self.widget
        target = getattr(app, '_f2_focus_target', None)
        if isinstance(target, dict) and target.get('widget') is w and target.get('start') is not None:
            row, span = target['row'], (target['start'], target['end'])
            close = getattr(app, '_close_dropdown', None)
            if close is not None:
                close()
            clear = getattr(app, '_clear_f2_target', None)
            if clear is not None:
                clear()
            w.focus_set()
            return (row, span, span[0]) if span[0] < span[1] else None
        ranges = w.tag_ranges('sel')
        if len(ranges) == 2:
            first, last = str(ranges[0]), str(ranges[1])
            row = int(first.split('.')[0])
            if row == int(last.split('.')[0]):
                span = (len(w.get(f'{row}.0', first)), len(w.get(f'{row}.0', last)))
                # 本文の選択: 範囲の中の紫の頭、紫が無ければカーソルのあった所
                odd = self._odd_in(row, w.get(f'{row}.0', f'{row}.end'), span)
                here = len(w.get(f'{row}.0', 'insert')) if str(w.index('insert')).split('.')[0] == str(row) else span[1]
                return row, span, odd if odd is not None else min(max(here, span[0]), span[1])
        return None

    def _typed_span(self):
        """今打って確定した範囲 (行, 始まり, 終わり) か None。IME の確定の記録（_just_committed_range: 最後の確定で、
        そのあと何もしていない時だけ）に、その前に隙間なく続く確定（本文の控えの確定の読み）を足した範囲。"""
        app, w = self.app, self.widget
        just = getattr(app, '_just_committed_range', None)
        got = just(w) if just is not None else None
        if not got:
            return None
        first, last = str(got[0]), str(got[1])
        row = int(first.split('.')[0])
        if row != int(last.split('.')[0]):
            return None
        start = len(w.get(f'{row}.0', first))
        end = len(w.get(f'{row}.0', last))
        if not self.quick:
            try:
                import analysis_work_app
                lines = w.get('1.0', 'end-1c').split('\n')
                found = sorted(analysis_work_app.line_readings(app, row - 1, lines) or (), key=lambda x: -x.end)
            except Exception:
                found = ()
            for x in found:
                if x.end == start:
                    start = x.start
        return row, start, end

    def _results(self):
        return getattr(self.app, '_quick_results' if self.quick else 'line_results', None) or ()

    def _answer_ready(self, row, text):
        results = self._results()
        result = results[row - 1] if row <= len(results) else None
        return bool(result) and result.get('original') == text and not result.get('pending')

    def _act_on_typed(self, typed, tries):
        """打った範囲の答えを待って（打った直後はまだ解析中が多い）、紫があればそこで開く。無ければ
        最後の語を再変換の選択状態にする。待つ間に何か押されたらやめる。"""
        if self._waiting != typed:
            return
        row, start, end = typed
        w = self.widget
        text = w.get(f'{row}.0', f'{row}.end')
        if not self._answer_ready(row, text) and tries < TYPED_WAIT_TRIES:
            w.after(TYPED_WAIT_MS, lambda: self._act_on_typed(typed, tries + 1))
            return
        self._waiting = None
        odd = self._odd_in(row, text, (start, end))
        if odd is not None:
            span = self.word_columns(row, text, odd)
            if span is not None:
                self._open_span(row, span, odd)
            return
        first = max(start, self.app._text_edge_column(w, row, text, end, -1))
        w.tag_remove('sel', '1.0', 'end')
        w.tag_add('sel', f'{row}.0+{first}c', f'{row}.0+{end}c')
        reconvert = getattr(self.app, '_on_quick_f2' if self.quick else '_on_f2_candidates', None)
        if reconvert is not None:
            reconvert(_F5(w))

    def _place_caret(self, row, text, span, column, original, reading):
        """開く前にカーソルがあった字の間に対応するかなの位置へ。範囲の頭で開いたら、範囲の中で紫が
        付いた最初の位置（無ければ範囲の頭）。"""
        at = column - span[0]
        if at == 0:
            at = self._first_odd(row, text, span)
        got = caret_column(original, reading, at, self._char_readings)
        self.widget.mark_set('insert', f'{START}+{got}c')
        self.widget.see('insert')

    def _odd_in(self, row, text, span):
        """範囲の中で紫が付いた最初の字の位置（行の中）か None。"""
        results = self._results()
        result = results[row - 1] if row <= len(results) else None
        if not result or result.get('original') != text:
            return None
        found = [max(x[0], span[0]) for x in result.get('odd_spans') or () if x[0] < span[1] and span[0] < x[1]]
        return min(found) if found else None

    def _first_odd(self, row, text, span):
        odd = self._odd_in(row, text, span)
        return 0 if odd is None else odd - span[0]

    def _char_readings(self, ch):
        """漢字1字の読みの候補（字ごとの区切りを取るだけ。答えには使わない）。"""
        got = []
        try:
            index = getattr(self.app, 'dict_index', None)
            if index is not None:
                got.extend(index.readings_for_surface(ch) or ())
        except Exception:
            pass
        try:
            one = self._reverse(ch)
            if one:
                got.append(one)
        except Exception:
            pass
        return [_hiragana(x) for x in got if x]

    def _owner(self):
        if self.quick:
            return 'quick'
        try:
            import analysis_work_app
            return analysis_work_app.owner(self.app)
        except Exception:
            return None

    def _color(self):
        w = self.widget
        try:
            dark = sum(w.winfo_rgb(w.cget('background'))) < 3 * 32768
        except Exception:
            dark = False
        w.tag_configure(TAG, background='#4a4326' if dark else '#fff2b8')
        w.tag_add(TAG, START, END)
        try:
            w.tag_raise('sel', TAG)
        except Exception:
            pass

    def current(self):
        return self.widget.get(START, END)

    def _write(self, text, keep_cursor=False):
        """範囲の字を text にする。開いてから確定までの書き換えは Undo 1回。"""
        st, w = self.state, self.widget
        if keep_cursor:
            w.mark_set(HERE, 'insert'); w.mark_gravity(HERE, 'right')
        if text != self.current():
            separators = w.cget('autoseparators')
            try:
                w.configure(autoseparators=False)
                if not st['wrote']:
                    w.edit_separator()
                    st['wrote'] = True
                w.delete(START, END)
                w.insert(START, text, (TAG,))
            finally:
                w.configure(autoseparators=separators)
            st['shown'] = text
            if not keep_cursor:
                w.mark_set('insert', END)
                w.see('insert')
            else:
                w.mark_set('insert', HERE)
            self._changed()
        elif not keep_cursor:
            w.mark_set('insert', END)
        if keep_cursor:
            w.mark_unset(HERE)
        w.tag_add(TAG, START, END)

    def _changed(self):
        change = None if self.quick else getattr(self.app, '_on_change', None)    # 簡易入力は <<Modified>> で
        if change is not None:
            change()

    def _say(self, text):
        status = getattr(self.app, 'status', None)
        if status is not None:
            status.config(text=text)

    def settle(self):
        """キーかマウスのあと: 外へ出たら終える。範囲の中の字が変わったら追う。"""
        st, w = self.state, self.widget
        if st is None:
            return
        if st['owner'] != self._owner():
            self._drop()        # タブが替わった: そのタブの字はそのまま
            return
        try:
            text = self.current()
            outside = w.compare('insert', '<', START) or w.compare('insert', '>', END)
        except Exception:
            self._drop()
            return
        if self.composing():
            return
        if self._back_before_it(st):
            return
        if not text:
            self.finish()
            return
        if outside:
            if text != st['shown']:
                st.update(shown=text, reading=None, choices=None, at=-1)
            self.leave()
            return
        if text != st['shown']:
            # IME がオンのまま押したスペースは、字になって入ってくる（キーの押しでは見えない）
            before = w.get('insert-1c', 'insert')
            if before in _SPACES and text.replace(before, '', 1) == st['shown']:
                w.delete('insert-1c', 'insert')
                # 押しが見えていたスペースなら、もう変換した（IME が字も入れてきた分を消すだけ）
                if time.monotonic() - self._space_at > SAME_SPACE_S:
                    self.convert_next()
                return
            st.update(shown=text, reading=None, choices=None, at=-1)
        w.tag_add(TAG, START, END)

    def _back_before_it(self, st):
        """Undo で開く前の行に戻った: 範囲はもう無い（変換も元に戻すもしない）。"""
        w = self.widget
        row = int(w.index(START).split('.')[0])
        if st['wrote'] and self.current() != st['shown'] and w.get(f'{row}.0', f'{row}.end') == st['line_before']:
            self._drop()
            return True
        return False

    def leave(self):
        """範囲から抜けた。字を変えていなければ元に戻す。変えていれば変換して終える。候補を選んでいる
        途中なら今の候補で確定。カーソルは抜けた先のまま。"""
        st = self.state
        if st is None:
            return
        text = self.current()
        if st['at'] >= 0 and text == st['shown']:
            self.finish()
        elif text == st['opened']:
            self._write(st['original'], keep_cursor=True)
            st['at'] = -1
            self.finish()
        else:
            st['shown'] = text
            self.convert_next(keep_cursor=True)
            self.finish()

    def convert_next(self, keep_cursor=False):
        st = self.state
        if st is None:
            return
        if st['choices'] is None:
            row = int(self.widget.index(START).split('.')[0])
            column = len(self.widget.get(f'{row}.0', START))
            st['reading'] = self.reading_of(row, column, self.current())
            st['choices'] = self.choices_for(st['reading'])
            st['at'] = -1
        if not st['choices']:
            self._say('この読みの変換が見つかりません')
            return
        st['at'] = (st['at'] + 1) % len(st['choices'])
        self._write(st['choices'][st['at']], keep_cursor)
        self._say(f"{HINT}（{st['at'] + 1}/{len(st['choices'])}）")

    def finish(self):
        """今の形で終える。解析はこの字で普通どおり。"""
        st, w = self.state, self.widget
        if st is None:
            return
        wrote = st['wrote']
        self._remember_conversion(st)
        row = int(w.index(START).split('.')[0])
        chosen = (w.get(f'{row}.0', f'{row}.end'), st['shown'], set(), st['line_before']) if not self.quick and st['at'] >= 0 and st['shown'] != st['reading'] else None
        self._drop()
        self._chosen = chosen
        self._kept_choices = None
        if chosen is not None:
            results = self._results()
            if row <= len(results) and results[row - 1]:
                self.on_answer(results[row - 1])
        if wrote:
            w.edit_separator()
        self._say('')

    def _remember_conversion(self, st):
        """選んだ変換を、IME で確定した語と同じように本文の控えへ（読みも持つ・メモリの中だけ）。
        読みの無い語に見えると、統合表示の自動反映が選んだ語を直してしまう。"""
        if self.quick or st['at'] < 0 or not st['reading'] or self.current() != st['shown']:
            return
        w = self.widget
        try:
            import analysis_work_app
            here = w.index('insert')
            w.mark_set('insert', END)
            try:
                analysis_work_app.remember(self.app, st['shown'], st['reading'])
            finally:
                w.mark_set('insert', here)
        except Exception:
            pass

    def on_answer(self, result):
        """本人が選んだ語を直す答えが来たら、右クリックの候補でその語を選び直したのと同じに覚える
        （_choose_word の記録。補正欄と統合表示の自動反映は、覚えた語で組み立てる）。"""
        chosen = self._chosen
        if chosen is None or not isinstance(result, dict):
            return
        if result.get('original') == chosen[3]:
            self._forget_choices()      # Undo で開く前の字に戻った: 覚えた語も戻す
            return
        if result.get('original') != chosen[0]:
            return
        app = self.app
        word = chosen[1]
        value = getattr(app, '_units_cache', {}).get((result.get('original'), result.get('corrected')))
        recorded = False
        for d in result.get('details') or ():
            if not (d and d[0] and d[1] and d[0] != d[1] and (d[0] in word or word in d[0])) or tuple(d[:2]) in chosen[2]:
                continue
            unit = next((u for u in (value[1] if value else ()) if d[1] in (u.get('base') or '')), None)
            if unit is None:
                continue
            if self._kept_choices is None:
                from choice_undo import _state
                self._kept_choices = _state(app.choices)
            chosen[2].add(tuple(d[:2]))
            surface = unit['base'].replace(d[1], d[0], 1)
            app.choices.record(unit['base'], surface, app._choice_reading(unit, dict(surface=surface, reading=None)),
                               unit.get('prev'), unit.get('next'))
            recorded = True
        if recorded:
            app.choices.save()
            app._invalidate_units_cache()
            app._choices_moved()

    def _forget_choices(self):
        kept, self._kept_choices = self._kept_choices, None
        if kept is None:
            return
        self._chosen[2].clear()
        app = self.app
        for name, value in kept.items():
            setattr(app.choices, name, dict(value))
        app.choices._revision = getattr(app.choices, '_revision', 0) + 1
        app.choices.save()
        app._invalidate_units_cache()
        app._choices_moved()

    def cancel(self):
        """開く前の字に戻す。"""
        st = self.state
        if st is None:
            return
        self._write(st['original'])
        st['at'] = -1
        self.finish()

    def _drop(self):
        w = self.widget
        self.state = None
        check_cursor(self.app)
        try:
            w.tag_remove(TAG, '1.0', 'end')
            w.mark_unset(START, END)
        except Exception:
            pass

    def keeps_row(self, row):
        """この行（1始まり）は今、範囲の中か（統合表示の自動反映が書き換えない）。"""
        if self.state is None:
            return False
        try:
            return int(self.widget.index(START).split('.')[0]) == row
        except Exception:
            return False

    # --- 読み ---------------------------------------------------------------
    def reading_of(self, row, column, surface):
        """surface の読みの平仮名。IME で確定した時の読み → 覚えた読み → IME の逆変換 → 形態素の読み。
        英字はそのまま。行の中の位置は確定の読み（打った所のもの）を当てるのに使う。"""
        out = []
        at = 0
        for start, end, reading in self._committed(row, column, surface):
            if start > at:
                out.append(self._read_part(row, column + at, surface[at:start]))
            out.append(_hiragana(reading))
            at = end
        if at < len(surface):
            out.append(self._read_part(row, column + at, surface[at:]))
        return ''.join(out)

    def _read_part(self, row, column, text):
        """確定の読みが無い所。語の途中で始まる・終わるなら、その語全体の読みから字の位置で切り出す（2026-11-03
        うにさん。2字の漢語の2字目だけを単独で読むと、打った読みと違う訓読みになる）。語に沿っていれば今までどおり。"""
        try:
            words = self._words_of(row)
        except Exception:
            words = ()
        end = column + len(text)
        if not any(s < column < e or s < end < e for s, e, _word, _reading in words):
            return self._read_gap(text)
        out = []
        at = column
        for s, e, word, reading in words:
            if e <= at or s >= end:
                continue
            if s > at:
                out.append(self._read_gap(text[at - column:s - column]))
            lo, hi = max(s, at), min(e, end)
            part = text[lo - column:hi - column]
            if lo == s and hi == e:
                got = self._word_reading(word, reading)
            else:
                got = self._cut_word(word, reading, lo - s, hi - s)
                if got is None:
                    got = self._read_gap(part)      # 最後の手段: その字だけで読む
            out.append(got)
            at = hi
        if at < end:
            out.append(self._read_gap(text[at - column:]))
        return ''.join(out)

    def _words_of(self, row):
        """その行の語 [(始まり, 終わり, 表記, 読み)]。"""
        fn = self.app.store._tokenize_fn
        line = self.widget.get(f'{row}.0', f'{row}.end')
        return [(t[3], t[4], t[0], t[2]) for t in fn(line)]

    def _word_reading(self, word, reading):
        try:
            known = self._remembered(word)
        except Exception:
            known = None
        for got in (known, reading):
            got = _hiragana(got) if got else None
            if _reads_as_kana(got):
                return got
        return self._read_gap(word)

    def _cut_word(self, word, reading, lo, hi):
        whole = self._word_reading(word, reading)
        first = cut_column(word, whole, lo, self._char_readings)
        last = cut_column(word, whole, hi, self._char_readings)
        return None if first is None or last is None or first >= last else whole[first:last]

    def _committed(self, row, column, surface):
        if self.quick:
            return []
        return self._committed_main(row, column, surface)

    def _committed_main(self, row, column, surface):
        """範囲の中に丸ごと入っている確定 [(範囲の中の始まり, 終わり, 読み)]。"""
        try:
            import analysis_work_app
            lines = self.widget.get('1.0', 'end-1c').split('\n')
            found = analysis_work_app.line_readings(self.app, row - 1, lines)
        except Exception:
            return []
        out = []
        for x in sorted(found or (), key=lambda x: x.start):
            start, end = x.start - column, x.end - column
            if not x.reading or end <= 0 or start >= len(surface) or (out and out[-1][1] > max(start, 0)):
                continue
            if 0 <= start and end <= len(surface):
                if surface[start:end] == x.surface:
                    out.append((start, end, x.reading))
                continue
            # 確定の途中で切れている: 確定の読みを字の位置で切り出す
            lo, hi = max(start, 0), min(end, len(surface))
            if x.surface[lo - start:hi - start] != surface[lo:hi]:
                continue
            reading = _hiragana(x.reading)
            first = cut_column(x.surface, reading, lo - start, self._char_readings)
            last = cut_column(x.surface, reading, hi - start, self._char_readings)
            if first is not None and last is not None and first < last:
                out.append((lo, hi, reading[first:last]))
        return out

    def _read_gap(self, text):
        return ''.join(part if ascii_part else self._read_run(part) for ascii_part, part in _split_ascii(text))

    def _read_run(self, text):
        plain = _hiragana(text)
        if _reads_as_kana(plain):
            return plain
        for read in (self._remembered, self._reverse, self._tokens):
            try:
                got = read(text)
            except Exception:
                got = None
            got = _hiragana(got) if got else None
            if _reads_as_kana(got):
                return got
        return plain

    def _remembered(self, text):
        known = getattr(self.app, 'ime_readings', None)
        found = known.readings_for(text) if known is not None else ()
        return next(iter(found), None)

    def _reverse(self, text):
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            return ime.phonetic(text) if ime.available else None

    def _tokens(self, text):
        fn = self.app.store._tokenize_fn
        return ''.join((t[2] or t[0]) if isinstance(t, tuple) else (t.reading if getattr(t, 'has_reading', True) and t.reading else t.surface) for t in fn(text))

    # --- 候補 ---------------------------------------------------------------
    def choices_for(self, reading):
        """IME の1つ目の変換、アプリの候補、読みそのものの順（同じ字は1つ）。"""
        got = []
        try:
            got.append(self._first_conversion(reading))
        except Exception:
            pass
        try:
            got.extend(self._listed(reading))
        except Exception:
            pass
        got.append(reading)
        return list(dict.fromkeys(x for x in got if x))

    def _first_conversion(self, reading):
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            return ime.convert(reading) if ime.available else None

    def _listed(self, reading):
        from vocabulary import find_known_readings_flex
        app = self.app
        listed = app._candidates_in_child(reading, reading, app.store, find_known_readings_flex,
                                          dict_index=getattr(app, 'dict_index', None), context_vec=getattr(app, 'context_vec', None),
                                          surrounding_words=[], attested=getattr(app, '_attested_surfaces', None),
                                          input_method=app.settings.get('input_method'))
        return [c['surface'] for c in listed or () if isinstance(c, dict) and c.get('surface') and c.get('kind') in KINDS]


def install(app, widget, quick=False):
    """欄の束縛の先頭に置く（キー名の束縛に黙らされず、'break' で後ろを止められる）。"""
    reinput = ReInput(app, widget, quick)
    tag = BIND_TAG + ('Quick' if quick else '')
    widget.bind_class(tag, '<KeyPress>', reinput.on_press)
    widget.bind_class(tag, '<KeyRelease>', reinput.on_release)
    widget.bind_class(tag, '<ButtonPress>', reinput.on_pointer)
    widget.bind_class(tag, '<ButtonRelease>', reinput.on_pointer_release)
    widget.bind_class(tag, '<FocusOut>', reinput.on_focus_out)
    hider = getattr(app, '_cursor_hider', None)
    if hider is None:
        hider = app._cursor_hider = CursorHider(app)
    widget.bind_class(tag, '<Motion>', hider.on_motion)
    widget.bind_class(tag, '<Enter>', hider.on_enter)
    widget.bindtags((tag,) + tuple(widget.bindtags()))
    # 補正欄は再入力変換の欄ではないが、同じように隠れるので動きを見る（ここが抜けていて戻らなかった）
    other = getattr(app, 'result_view', None)
    if not quick and other is not None and other is not widget:
        watch_tag = BIND_TAG + 'Pane'
        other.bind_class(watch_tag, '<Motion>', hider.on_motion)
        other.bind_class(watch_tag, '<Enter>', hider.on_enter)
        other.bindtags((watch_tag,) + tuple(other.bindtags()))
    return reinput


class ListKeys:
    """再変換（F5）の候補一覧のキー（2026-11-03 うにさん「再変換と融合」）。キーはこの一覧へ来る。
        候補を動かしていない: Space → その範囲で再入力変換 ／ Ctrl 2回 → 同じ
        候補を動かした:       Ctrl を単独で押して離す → その候補で決定（Space と同じ）
    「動かした」は、今の選択が開いた時の選択と違うこと（矢印で動かして戻せば動かしていない）。"""

    def __init__(self, app, listbox):
        self.app = app
        self.listbox = listbox
        self.first = None
        self.alone = False

    def remember_first(self):
        try:
            self.first = tuple(self.listbox.curselection())
        except Exception:
            self.first = None

    def moved(self):
        try:
            return self.first is not None and tuple(self.listbox.curselection()) != self.first
        except Exception:
            return False

    def owner(self):
        app = self.app
        target = getattr(app, '_f2_focus_target', None)
        widget = target.get('widget') if isinstance(target, dict) else None
        for reinput in (getattr(app, '_reinput', None), getattr(app, '_quick_reinput', None)):
            if reinput is not None and reinput.widget is widget:
                return reinput
        return None

    def press(self, event):
        reinput = self.owner()
        key = getattr(event, 'keysym', '')
        if key in _CONTROL:
            self.alone = True
            if reinput is not None:
                reinput.on_press(event)
            return None
        self.alone = False
        if reinput is None:
            return None
        reinput.other_key(event)
        hider = getattr(self.app, '_cursor_hider', None)
        if hider is not None and key not in _MODIFIERS:
            hider.hide(self.listbox)
        if (_is_space(event) and not self.moved()
                and getattr(self.app, '_dropdown_typing', None) is None):
            reinput.start()
            return 'break'
        return None

    def release(self, event):
        reinput = self.owner()
        if getattr(event, 'keysym', '') not in _CONTROL:
            self.alone = False
            return None
        alone, self.alone = self.alone, False
        if reinput is None:
            return None
        if alone and self.moved():
            reinput._forget_taps()
            self.app._dropdown_pick()
            return 'break'
        reinput.on_release(event)
        return None

    def pointer(self, event=None):
        self.alone = False
        reinput = self.owner()
        if reinput is not None:
            reinput._forget_taps()
        return None


def install_on_list(app, listbox):
    """候補一覧の束縛の先頭に置く。開いた時の選択は、一覧ができたあとで控える。"""
    keys = ListKeys(app, listbox)
    tag = f'{LIST_TAG}{listbox}'
    bound = []
    for sequence, func in (('<KeyPress>', keys.press), ('<KeyRelease>', keys.release), ('<ButtonPress>', keys.pointer)):
        bound.append((sequence, listbox.bind_class(tag, sequence, func)))
    hider = getattr(app, '_cursor_hider', None)
    if hider is not None:
        bound.append(('<Motion>', listbox.bind_class(tag, '<Motion>', hider.on_motion)))
        bound.append(('<FocusOut>', listbox.bind_class(tag, '<FocusOut>', hider.on_focus_out)))
        hider.add(listbox)
    listbox.bindtags((tag,) + tuple(listbox.bindtags()))

    # 一覧ごとの束縛は、一覧が閉じた時に外す（2026-11-08）: bind_class の束縛は Tk が消さないので、開くたびに
    # キーの受け手（とそれが持つアプリ・窓）が残っていた（tests_gui_dropdown_height が「閉じた窓が残っている」で落ちていた）
    def forget(event=None):
        if event is not None and event.widget is not listbox:
            return
        # bind_class の手続きは root の名簿（_tclCommands）に載る。一覧の deletecommand で消すと root の名簿に名前が
        # 残り、窓を閉じる時の root.destroy が「can't delete Tcl command」で落ちた（Python 3.11・CI・2026-11-10）。
        # 載せた root から消す（root の名簿からも外れる）
        owner = listbox._root()
        for sequence, name in bound:
            try:
                listbox.tk.call('bind', tag, sequence, '')
            except Exception:
                pass
            try:
                owner.deletecommand(name)
            except Exception:
                pass
        del bound[:]
    listbox.bind('<Destroy>', forget, add='+')
    listbox.after_idle(keys.remember_first)
    return keys
