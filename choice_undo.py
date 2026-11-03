# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""補正欄の選び直し（再変換の候補から選ぶ・元に戻す）を、Ctrl+Z / Ctrl+Y の履歴に入れる（2026-11-01 うにさん
「補正欄の再変換が、Undo履歴に残っていないので、履歴に残す」）。

補正欄での選び直しは本文を書き換えず、選び直しの記憶（last_choice）だけを変える。text_format（太字など）と
同じく、本文の Undo の流れに「本文以外の一手」として入れる（analysis_work の undo_hooks・next_step_seq）。
一手が取られるのは、本文がその選び直しをしたときのままのときだけ（あとの本文の編集を先に戻す）。
"""
from analysis_work import next_step_seq, observe_text

HISTORY_LIMIT = 100
_FIELDS = ('_readings', '_units', '_contexts')


def _state(choices):
    return {name: dict(getattr(choices, name, None) or {}) for name in _FIELDS}


class ChoiceUndo:
    def __init__(self, app, widget):
        self.app, self.widget = app, widget
        self.history, self.redo = [], []
        observe_text(widget)
        observers = widget._correctnote_observers
        observers.setdefault('undo_hooks', []).append(self.undo_step)
        observers.setdefault('changed', []).append(self.changed)
        self.shown_mark = None      # (行, 位置, 補正欄に出した語): 補正欄の描き直しのあとも引き直す

    def _text(self):
        return self.widget.get('1.0', 'end-1c')

    def before(self):
        """選び直しの前に呼ぶ。戻り値を after に渡す。"""
        choices = getattr(self.app, 'choices', None)
        return None if choices is None else _state(choices)

    def after(self, before, where=None):
        """選び直しのあとに呼ぶ。記憶が変わっていれば一手として積む。
        where: (行, 語の始まり, 元の表記, 選んだ表記)。戻したとき・やり直したときに下線を引く場所。"""
        choices = getattr(self.app, 'choices', None)
        if before is None or choices is None:
            return False
        now = _state(choices)
        if now == before:
            return False
        self.history.append((self._text(), before, now, next_step_seq(self.widget), where))
        del self.history[:-HISTORY_LIMIT]
        self.redo.clear()
        return True

    def due_step_seq(self, kind):
        """Ctrl+Z / Ctrl+Y がいま取る一手の番号か None（analysis_work._hooks_in_turn）。"""
        stack = self.history if kind == 'undo' else self.redo
        if not stack or stack[-1][0] != self._text():
            return None
        return stack[-1][3]

    def undo_step(self, kind):
        stack, other = (self.history, self.redo) if kind == 'undo' else (self.redo, self.history)
        if not stack or stack[-1][0] != self._text():
            return False
        entry = stack.pop()
        where = entry[4] if len(entry) > 4 else None
        row_first = getattr(self.app, '_choice_row_first', None)
        self._row_first = (lambda: row_first(where[0])) if where and row_first is not None else None
        self._restore(entry[1] if kind == 'undo' else entry[2], kind)
        other.append(entry)
        if len(entry) > 4 and entry[4]:
            try:
                self._mark(entry[4], kind)
            except Exception:
                pass
        return True

    RESULT_TAG = 'undo_feedback'

    def _mark(self, where, kind):
        """Undo を示す下線（本文の Undo と同じ undo_feedback）を、本文の語と補正欄の語に引く
        （2026-11-01 うにさん「元に戻した時に、Undoを示す下線を引く」）。次の本文の編集で消える。
        where: (行, 位置, 本文の語, 戻したとき補正欄に出る語, やり直したとき補正欄に出る語)
        （古い形 (行, 位置, 元の表記, 選んだ表記) も受ける）。"""
        if len(where) == 4:
            row, start, base, chosen = where
            where = (row, start, base, base, chosen)
        row, start, source, undo_shows, redo_shows = where
        mark(self.app, row, start, source, undo_shows if kind == 'undo' else redo_shows, redo=(kind == 'redo'))
        self._result_marked = True

    def _restore(self, state, kind='undo'):
        app = self.app
        choices = app.choices
        for name, value in state.items():
            setattr(choices, name, dict(value))
        choices._revision = getattr(choices, '_revision', 0) + 1
        try:
            choices.save()
        except Exception:
            pass
        steps = ['_invalidate_units_cache', '_choices_moved', '_render_corrected', '_update_status']
        if not hasattr(app, '_choices_moved'):
            steps[1] = '_invalidate_analysis_cache'
        for name in steps:
            if name == '_render_corrected' and getattr(self, '_row_first', None) is not None:
                try:
                    self._row_first()       # 戻した行を補正欄へすぐ出し、解析し直しでも先に（2026-11-01）
                except Exception:
                    pass
            fn = getattr(app, name, None)
            if fn is not None:
                try:
                    fn()
                except Exception:
                    pass
        try:
            app.status.config(text='選び直しを元に戻しました' if kind == 'undo' else '選び直しをやり直しました')
        except Exception:
            pass

    def changed(self, args=None):
        if args and tuple(args[:2]) in (('edit', 'undo'), ('edit', 'redo')):
            # 本文の Undo（類語の入れ替えなど本文の編集）の下線を、補正欄にも映す（本文の下線を塗ったあとで）。
            # 選び直しの戻しの下線は、本文の Undo が来たら終わり
            self.shown_mark = None
            try:
                self.widget.after_idle(lambda: self.widget.after_idle(lambda: mirror(self.app)))
            except Exception:
                pass
        if args and args[0] in ('insert', 'delete', 'replace'):
            self.shown_mark = None
            if getattr(self, '_result_marked', False):
                self._result_marked = False
                try:
                    self.app.result_view.tag_remove(self.RESULT_TAG, '1.0', 'end')
                except Exception:
                    pass
        # 本文を新しく編集したら、やり直せる選び直しは終わり（本文の Undo と同じ）
        if (self.redo and args and args[0] in ('insert', 'delete', 'replace')
                and not getattr(self.widget, '_correctnote_replay_depth', 0)):
            self.redo.clear()


def mark(app, row, start, source, shown, redo=False):
    """本文の row 行の source（start に近いもの）と、補正欄の row 行の shown に、Undo の下線を引く。"""
    editor = app.editor
    feedback = getattr(editor, '_correctnote_undo_feedback', None)
    try:
        line = editor.get('%d.0' % row, '%d.end' % row)
    except Exception:
        return
    at = _nearest(line, source, start)
    if feedback is not None and at is not None:
        offset = int(editor.count('-chars', '1.0', '%d.0' % row)[0] or 0) if row > 1 else 0
        feedback._clear_color()
        feedback._queue_color([(offset + at, offset + at + len(source))], redo=redo)
    undo = getattr(app, '_choice_undo', None)
    if undo is not None:
        undo.shown_mark = (row, start, shown)
    mirror(app)


def mirror(app):
    """補正欄の Undo の下線を引き直す: 選び直しの戻しで出した語（shown_mark）と、本文の Undo の下線
    （undo_feedback）が付いた語の、補正欄の同じ行の同じ語。補正欄の描き直し（_render_corrected）のあとにも呼ぶ。
    2026-11-01 うにさん「類語から元に戻した時は本文に出て補正欄に出ない」。"""
    result = getattr(app, 'result_view', None)
    editor = getattr(app, 'editor', None)
    if result is None or editor is None:
        return
    try:
        result.tag_remove(ChoiceUndo.RESULT_TAG, '1.0', 'end')
    except Exception:
        return
    texts = getattr(app, 'line_texts', None) or []
    spans = []
    undo = getattr(app, '_choice_undo', None)
    shown = getattr(undo, 'shown_mark', None) if undo is not None else None
    if shown:
        row, start, word = shown
        if 0 < row <= len(texts):
            at = _nearest(texts[row - 1], word, start)
            if at is not None:
                spans.append((row, at, at + len(word)))
    try:
        ranges = editor.tag_ranges('undo_feedback')
    except Exception:
        ranges = ()
    for first, last in zip(ranges[0::2], ranges[1::2]):
        try:
            row, col = (int(x) for x in str(editor.index(first)).split('.'))
            end_row = int(str(editor.index(last)).split('.')[0])
            word = editor.get(first, last)
        except Exception:
            continue
        if end_row != row or not word.strip() or not (0 < row <= len(texts)):
            continue
        at = _nearest(texts[row - 1], word, col)
        if at is not None and not any(r == row and a < at + len(word) and at < b for r, a, b in spans):
            spans.append((row, at, at + len(word)))
    if not spans:
        return
    feedback = getattr(editor, '_correctnote_undo_feedback', None)
    color = feedback._underline_color() if feedback is not None else '#b65000'
    try:
        result.tag_configure(ChoiceUndo.RESULT_TAG, underline=1, underlinefg=color)
        for row, a, b in spans:
            result.tag_add(ChoiceUndo.RESULT_TAG, '%d.0+%dc' % (row, a), '%d.0+%dc' % (row, b))
        result.tag_raise(ChoiceUndo.RESULT_TAG)
    except Exception:
        return
    if undo is not None:
        undo._result_marked = True


def _nearest(text, word, start):
    """text の中で、start にいちばん近い word の位置（無ければ None）。"""
    if not word:
        return None
    best, i = None, text.find(word)
    while i >= 0:
        if best is None or abs(i - start) < abs(best - start):
            best = i
        i = text.find(word, i + 1)
    return best


def install(app):
    undo = getattr(app, '_choice_undo', None)
    if undo is None:
        undo = app._choice_undo = ChoiceUndo(app, app.editor)
    return undo
