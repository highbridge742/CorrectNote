# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""スクロールの記録（2026-11-07・うにさん「右ドラッグを離すと元の行に戻ることがある」の手がかり用）。

既定は入り（2026-11-07 うにさん）。環境変数 CN_SCROLL_TRACE=0 か、デバッグメニューの「スクロールの記録」で切れる（切った時は次の起動も切り）。
本文の欄の一番上の行が変わるたびに、1行の JSON を tools_local\\scroll_trace\\scroll_trace.log に足す:
時刻・前後の一番上の行番号・カーソルの行番号・動かした関数（呼び出し元を3段）・その時の操作
（右ドラッグ中か、右ボタン／ホイール／キーから何秒か）。**本文の文字は一切残さない。**
ファイルは上限（MAX_BYTES）を超えたら古い方から捨てる。書き出しは1秒ごとにまとめて。

切りのときは何も掛けない（本文の欄の関数も束縛も元のまま）。記録の置き場が無ければ作る。"""
import json
import os
import sys
import time

MAX_BYTES = 1024 * 1024
FLUSH_MS = 1000
MOVER_WINDOW_S = 0.25        # この間に呼ばれた Python の動かし手を、動いた理由とみなす
_METHODS = ('see', 'yview', 'yview_moveto', 'yview_scroll')


def _folder(app):
    folder = getattr(app, '_scroll_trace_dir', None)      # app が app_dir() から渡す
    if folder:
        return folder
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools_local', 'scroll_trace')


def log_path(app):
    return os.path.join(_folder(app), 'scroll_trace.log')


def enabled(app):
    state = getattr(app, '_scroll_trace', None)
    return bool(state and state.get('on'))


def wanted(app):
    """入れるか。既定は入り（2026-11-07 うにさん「入れてください」）。環境変数 CN_SCROLL_TRACE=0、またはデバッグメニューで
    切った時（settings の scroll_trace が False・次の起動も切り）は切り。CN_SCROLL_TRACE=1 はいつも入り。"""
    value = os.environ.get('CN_SCROLL_TRACE')
    if value in ('0', '1'):
        return value == '1'
    settings = getattr(app, 'settings', None)
    try:
        return settings.get('scroll_trace') is not False
    except Exception:
        return True


def install_from_env(app):
    if wanted(app):
        enable(app)


def choose(app, on):
    """デバッグメニューのチェック。切った・入れたを設定に残す（次の起動もそのまま）。"""
    settings = getattr(app, 'settings', None)
    try:
        settings.set('scroll_trace', bool(on))
        settings.save()
    except Exception:
        pass
    if on:
        return enable(app)
    disable(app)
    return False


def _top_row(widget):
    try:
        return int(widget.index('@0,0').split('.')[0])
    except Exception:
        return None


def _caller(skip=2, depth=3):
    """呼び出し元の関数名（ファイル名:関数:行）を depth 段。"""
    out = []
    try:
        frame = sys._getframe(skip)
        while frame is not None and len(out) < depth:
            code = frame.f_code
            out.append('%s:%s:%d' % (os.path.basename(code.co_filename), code.co_name, frame.f_lineno))
            frame = frame.f_back
    except Exception:
        pass
    return out


def enable(app):
    if enabled(app):
        return True
    editor = getattr(app, 'editor', None)
    root = getattr(app, 'root', None)
    if editor is None or root is None:
        return False
    state = getattr(app, '_scroll_trace', None) or {}
    state.update(on=True, lines=[], flush_job=None, mover=None, top=_top_row(editor),
                 last={'right_release': None, 'right_press': None, 'wheel': None, 'key': None})
    app._scroll_trace = state
    # 1) Python から本文の欄を動かす関数を包む（誰が動かしたかを覚えるだけ。動きは元のまま）
    wrapped = {}
    for name in _METHODS:
        real = getattr(type(editor), name)

        def wrapper(*args, _real=real, _name=name):
            if enabled(app) and args:
                state['mover'] = (time.monotonic(), _name, _caller())
            return _real(editor, *args)
        wrapped[name] = wrapper
        setattr(editor, name, wrapper)
    state['wrapped'] = wrapped
    # 右ドラッグの「端でカーソルを戻す」（_warp_pointer）も、戻す前後のカーソルの高さだけ残す（2026-11-07・1行目に着いた
    # 直後に約30行戻る件の手がかり。本文の字は無い）
    real_warp = getattr(app, '_warp_pointer', None)
    if real_warp is not None and 'warp' not in state:
        def warp(widget, x, y, _real=real_warp):
            try:
                before = widget.winfo_pointery()
            except Exception:
                before = None
            got = _real(widget, x, y)
            try:
                after = widget.winfo_pointery()
                root_y = widget.winfo_rooty()
            except Exception:
                after = root_y = None
            if enabled(app):
                drag = getattr(app, '_drag', None) or {}
                _write(app, dict(event='warp', pointer_before=before, pointer_after=after, target=(None if root_y is None else root_y + y),
                                 result=str(got), last_y=drag.get('last_y'), top=_top_row(editor)))
            return got
        app._warp_pointer = warp
        state['warp'] = real_warp
    # 2) 一番上の行が変わったかは、本文の欄の yscrollcommand の前で見る（Tk 自身が動かしたときもここに来る）
    try:
        previous = editor.cget('yscrollcommand')
    except Exception:
        previous = ''
    state['previous_command'] = previous
    forward = getattr(app, '_on_editor_scroll', None)

    def on_scroll(first, last):
        try:
            _view_moved(app, editor)
        except Exception:
            pass
        if forward is not None:
            return forward(first, last)
    editor.config(yscrollcommand=on_scroll)
    # 3) その時の操作（右ボタン・ホイール・キー）の時刻。欄の束縛の先頭に札を1枚足して見るだけ（'break' で止めない）。
    #    bind_all では、欄の束縛が 'break' を返すと届かない
    tag = 'CorrectNoteScrollTrace'
    def note(kind):
        def handler(event=None):
            if enabled(app):
                state['last'][kind] = time.monotonic()
        return handler
    for sequence, kind in (('<ButtonRelease-3>', 'right_release'), ('<ButtonPress-3>', 'right_press'),
                           ('<MouseWheel>', 'wheel'), ('<KeyPress>', 'key')):
        try:
            root.bind_class(tag, sequence, note(kind))
        except Exception:
            pass
    for widget in (editor, getattr(app, 'result_view', None)):
        try:
            if widget is not None and tag not in widget.bindtags():
                widget.bindtags((tag,) + tuple(widget.bindtags()))
        except Exception:
            pass
    state['tag'] = tag
    _write(app, dict(event='start', top=state['top']))
    return True


def disable(app):
    state = getattr(app, '_scroll_trace', None)
    if not state or not state.get('on'):
        return
    editor = getattr(app, 'editor', None)
    for name in _METHODS:
        try:
            if name in editor.__dict__:
                del editor.__dict__[name]
        except Exception:
            pass
    if state.pop('warp', None) is not None:
        try:
            app.__dict__.pop('_warp_pointer', None)       # the class's own again
        except Exception:
            pass
    try:
        forward = getattr(app, '_on_editor_scroll', None)
        editor.config(yscrollcommand=forward if forward is not None else state.get('previous_command', ''))
    except Exception:
        pass
    for widget in (editor, getattr(app, 'result_view', None)):
        try:
            tags = tuple(widget.bindtags())
            if state.get('tag') in tags:
                widget.bindtags(tuple(t for t in tags if t != state.get('tag')))
        except Exception:
            pass
    _write(app, dict(event='stop'))
    state['on'] = False
    flush(app)


def _since(stamp, now):
    return None if stamp is None else round(now - stamp, 3)


def _view_moved(app, editor):
    state = app._scroll_trace
    top = _top_row(editor)
    if top is None or top == state.get('top'):
        return
    before, state['top'] = state.get('top'), top
    now = time.monotonic()
    mover = state.get('mover')
    if mover is not None and now - mover[0] <= MOVER_WINDOW_S:
        by = dict(method=mover[1], callers=mover[2], ago=round(now - mover[0], 3))
    else:
        by = dict(method='Tk', callers=[])      # Tk 自身（キーの既定の束縛など）
    drag = getattr(app, '_drag', None)
    try:
        insert = int(editor.index('insert').split('.')[0])
    except Exception:
        insert = None
    last = state['last']
    try:
        pointer = editor.winfo_pointery() - editor.winfo_rooty()
    except Exception:
        pointer = None
    _write(app, dict(event='move', top_before=before, top_after=top, insert_row=insert, by=by, pointer_y=pointer,
                     drag_last_y=(drag or {}).get('last_y') if isinstance(drag, dict) else None,
                     right_drag=bool(drag and drag.get('mode') == 'scroll'),
                     since=dict((k, _since(v, now)) for k, v in last.items())))


def _write(app, record):
    state = app._scroll_trace
    record = dict(t=time.strftime('%Y-%m-%d %H:%M:%S') + ('.%03d' % int((time.time() % 1) * 1000)), **record)
    state['lines'].append(json.dumps(record, ensure_ascii=False))
    if state.get('flush_job') is None:
        try:
            state['flush_job'] = app.root.after(FLUSH_MS, lambda: flush(app))
        except Exception:
            flush(app)


def flush(app):
    state = getattr(app, '_scroll_trace', None)
    if not state:
        return
    state['flush_job'] = None
    lines, state['lines'] = state.get('lines') or [], []
    if not lines:
        return
    try:
        folder = _folder(app)
        os.makedirs(folder, exist_ok=True)
        path = log_path(app)
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        if os.path.getsize(path) > MAX_BYTES:
            with open(path, 'rb') as f:
                data = f.read()
            keep = data[-MAX_BYTES // 2:]
            cut = keep.find(b'\n')
            with open(path, 'wb') as f:
                f.write(keep[cut + 1:] if cut >= 0 else keep)
    except Exception:
        pass
