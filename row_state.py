# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""行の状態を見る道具（2026-11-20 うにさんの報告「140行が直らず紫も無い。2行下の同じ文は直る」「20行で右の欄に入力途中のような
形」の調べ）。デバッグの窓の「行の状態…」から開く。

行番号を入れる（既定は今のカーソルの行と前後2行）と、**行の字は出さずに**次を表にする。うにさんが画面の表をそのまま写して
送れるように、表をコピーするボタンを付ける。読むだけで、何も変えない。
  ・答えの元の字と今の字が一致しているか
  ・解析待ち／解き直し待ち（控えから戻して語彙が動いた等）／控えから戻した答え／表示の単位だけ組む行
  ・重い見直しが済んだか
  ・カーソルの行か・統合表示の自動反映をカーソルの行として後回しにしているか
  ・断った印（統合の自動反映を Ctrl+Z で戻した行の字）・断った語（今後直さない）に掛かるか
  ・同じ字の行・見えない字だけが違う行（違いの種類）
  ・右の欄の字が答えと一致しているか
CN_ROW_STATE_TOOL=0 でボタンを出さない。
"""
import os
import re
import unicodedata

ZERO_WIDTH = '​‌‍⁠﻿'
SAME_LIMIT = 6


def enabled(environ=None, frozen=None):
    """「行の状態…」のボタンを出すか。2026-11-23 うにさん「行の状態と、解析の記録のボタンもリリースでは消してください。
    このボタンは開発のほうは残します」: 開発版（.py で動かす時）は出す・EXE（Store 版を含む）は出さない。
    CN_ROW_STATE_TOOL=0 ならどちらも出さない、=1 なら EXE でも出す"""
    import sys
    environ = os.environ if environ is None else environ
    frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else frozen
    value = environ.get('CN_ROW_STATE_TOOL')
    if value in ('0', '1'):
        return value == '1'
    return not frozen


# --- 見えない字の違い ----------------------------------------------------------------
_STEPS = (
    ('末尾の空白', lambda t: t.rstrip(' \t　')),
    ('全角空白', lambda t: t.replace('　', ' ')),
    ('ゼロ幅の字', lambda t: ''.join(c for c in t if c not in ZERO_WIDTH)),
    ('NBSP', lambda t: t.replace(' ', ' ')),
    ('異体字セレクタ', lambda t: re.sub('[︀-️]', '', t)),
    ('タブ', lambda t: t.replace('\t', ' ')),
    ('全角半角・互換の字', lambda t: unicodedata.normalize('NFKC', t)),
)


def normalize(text):
    for _name, fn in _STEPS:
        text = fn(text)
    return text


def differences(a, b):
    """見た目が同じになる2行の、違いの種類（無ければ空）。"""
    if a == b:
        return []
    kinds = []
    for name, fn in _STEPS:
        if fn(a) != a or fn(b) != b:
            kinds.append(name)
    return kinds


def parse_rows(text, last):
    """'140, 142, 20-21' → [140, 142, 20, 21]（1〜last の中だけ）。"""
    out = []
    for part in re.split(r'[,\s、，]+', text or ''):
        if not part:
            continue
        m = re.fullmatch(r'(\d+)\s*[-–〜~]\s*(\d+)', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            for r in range(min(a, b), max(a, b) + 1):
                if 1 <= r <= last and r not in out:
                    out.append(r)
        elif part.isdigit():
            r = int(part)
            if 1 <= r <= last and r not in out:
                out.append(r)
    return out[:60]


# 行番号の欄の既定（2026-11-21 07:39Z うにさん「行のデバッグの行番号には、デフォルトで1－50を入れておいてください」）。
# 前に入れた値を覚える作りは無い。欄が空・読めない時もこの範囲。CN_ROW_STATE_DEFAULT_RANGE=0 で前の形（カーソルの行と
# 前後2行）
DEFAULT_RANGE = '1-50'


def default_range_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_DEFAULT_RANGE') != '0'


def default_text(app):
    return DEFAULT_RANGE if default_range_on() else ', '.join(str(r) for r in default_rows(app))


def default_rows_for(app, last):
    if default_range_on():
        return parse_rows(DEFAULT_RANGE, last) or [1]
    return default_rows(app)


def default_rows(app):
    try:
        row = int(str(app.editor.index('insert')).split('.')[0])
    except Exception:
        row = 1
    return list(range(max(1, row - 2), row + 3))


# --- 1行の状態 --------------------------------------------------------------------
def _yes(flag):
    return 'はい' if flag else 'いいえ'


def row_state(app, row, lines=None, norms=None):
    """行 row（1から）の状態（字の中身は入れない）。"""
    if lines is None:
        lines = app.editor_source_text().split('\n')
    i = row - 1
    line = lines[i] if 0 <= i < len(lines) else ''
    results = getattr(app, 'line_results', None) or ()
    result = results[i] if 0 <= i < len(results) else None
    out = {'行': row}
    if not result:
        out['答えと字'] = '答え無し'
    else:
        out['答えと字'] = '一致' if result.get('original') == line else '不一致'
    flags = []
    todo = getattr(app, '_analyze_todo', None) or []
    pos = getattr(app, '_analyze_pos', 0) or 0
    waiting = i in set(todo[pos:]) if isinstance(todo, list) else False
    deferred = bool(result and result.get('deferred_stages'))
    units_only = (i in set(getattr(app, '_units_only_rows', None) or ())) or (
        waiting and getattr(app, '_analyze_units_only', False))
    restored = False
    try:
        import tab_analysis
        restored = bool(tab_analysis.restored_without_proof(result))
    except Exception:
        pass
    if state2_on():
        # 2026-11-21 06:37Z うにさん「行の縦線が消えているのに、行のデバッグを見ると、解析待ち・解き直し待ち・控えから
        # 戻した答え待ち と出る」: 縦線（行番号の右の印・app._line_analysis_state）と同じ見方にそろえ、待ちでないものを
        # 待ちと書かない。縦線は「答えを出して見せているか」。
        # ・解析待ち: 答えが無い・仮の答え・今の解析の列に残っていて、前の答えも使えない時だけ（列に残っているだけで、
        #   答えを見せている行＝控えから戻した行の「組むだけ」の残りなどは待ちではない）
        # ・答えあり・重い確かめ待ち: 答えは出ていて見せている。重い段を後で確かめる（カーソルを置くと先に・解き直しの
        #   列に入るのは手が止まった時）。前は「解き直し待ち」
        # ・控えから戻した答え（そのまま使う）: 待ちではない（前は待ちのように並んでいた）
        # ・組むだけ: 表示の単位だけを組む残り（答えは変わらない）
        # CN_ROW_STATE_STATE2=0 で前の形
        live = False
        try:
            live = bool(app._foreground_analysis_pending())
        except Exception:
            live = True
        shown = _gutter_state(app, row)
        if not result or result.get('pending') or (waiting and live and shown == 'pending'):
            flags.append('解析待ち')
        elif deferred:
            flags.append('答えあり・重い確かめ待ち')
        if restored:
            flags.append('控えから戻した答え（そのまま使う）')
        if units_only and waiting and live:
            flags.append('組むだけの残り')
    else:
        if not result or result.get('pending') or waiting:
            flags.append('解析待ち')
        if deferred:
            flags.append('解き直し待ち')
        if restored:
            flags.append('控えから戻した答え')
        if units_only:
            flags.append('組むだけ')
    out['状態'] = '・'.join(flags) or '済み'
    if state2_on():
        out['縦線'] = {'pending': 'あり（解析待ち）', 'incomplete': 'あり（途中まで）', 'done': 'なし'}.get(
            _gutter_state(app, row), '?')
    out['重い見直し'] = '待ち' if (deferred or (result and result.get('pending'))) else ('済み' if result else '—')
    try:
        cursor = int(str(app.editor.index('insert')).split('.')[0])
    except Exception:
        cursor = None
    out['カーソルの行'] = _yes(cursor == row)
    unified = False
    try:
        unified = bool(app._layout_is_unified())
    except Exception:
        pass
    later = False
    if unified and cursor == row and result and result.get('changed'):
        try:
            later = app.editor.get('%d.0' % row, '%d.end' % row) == result.get('original')
        except Exception:
            later = False
    out['統合で後回し'] = _yes(later) if unified else '（分割表示）'
    try:
        declined = app._autofix_declined_rows()
    except Exception:
        declined = set()
    out['断った印'] = _yes(line in declined)
    kinds_row, kinds_word = stop_records(app, row, line) if records_on() else ([], [])
    if records_on():
        out['断った印'] = _yes(bool(kinds_row))
    blocked = False
    decisions = getattr(app, 'decisions', None)
    if decisions is not None and line:
        try:
            blocked = any(word and word in line for word in getattr(decisions, '_protected', ()) or ())
            if result and result.get('corrected') and result.get('corrected') != line:
                blocked = blocked or bool(decisions.blocks(line, result.get('corrected')))
        except Exception:
            blocked = False
    out['断った語'] = _yes(blocked)
    if records_on():
        if blocked and not kinds_word:
            kinds_word.append('この直しへの拒否')
        out['断った語'] = _yes(bool(kinds_word))
        out['止める記録'] = '・'.join(kinds_row + kinds_word) or '—'
    same, near = [], []
    if line.strip():
        if norms is None:
            norms = [normalize(t) for t in lines]
        key = normalize(line)
        for k, other in enumerate(lines):
            if k == i or not other.strip():
                continue
            if other == line:
                same.append(k + 1)
            elif norms[k] == key:
                near.append('%d（%s）' % (k + 1, '・'.join(differences(line, other)) or '?'))
    out['同じ字の行'] = ', '.join(str(r) for r in same[:SAME_LIMIT]) + (' …' if len(same) > SAME_LIMIT else '') or '—'
    out['見えない字だけ違う行'] = ', '.join(near[:SAME_LIMIT]) + (' …' if len(near) > SAME_LIMIT else '') or '—'
    if inputs_on():
        try:
            out.update(input_columns(app, i, lines, result, same))
        except Exception:
            pass
    if text_on():
        out['メモ欄の字'] = visible(line)
        try:
            right = (result or {}).get('corrected') if unified else app.result_view.get('%d.0' % row, '%d.end' % row)
        except Exception:
            right = None
        out['補正欄の字'] = '（同じ）' if right == line else ('—' if right is None else visible(right))
    if unified:
        out['右の欄'] = '（統合表示）'
    else:
        try:
            shown = app.result_view.get('%d.0' % row, '%d.end' % row)
            want = (result or {}).get('corrected')
            out['右の欄'] = '答え無し' if want is None else ('一致' if shown == want else '不一致')
        except Exception:
            out['右の欄'] = '?'
    return out


# --- 行の補正を止めうる記録（2026-11-21 うにさん: 140行は再変換メニューに「元に戻す」「使わない」があり、過去に元に戻した
# と思う。それなのに表の「断った印」「断った語」は「いいえ」だった）。前は統合の自動反映を Ctrl+Z で戻した字（断った印）と
# 守る語・この行の直しへの拒否（断った語）しか見ていなかった。補正を止めうる記録の種類を全部拾い、種類の名だけ出す。
# CN_ROW_STATE_RECORDS=0 で前の形
def records_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_RECORDS') != '0'


def _str_values(mapping):
    for key, value in (mapping or {}).items():
        for x in (key if isinstance(key, tuple) else (key,)) + ((value,) if not isinstance(value, dict) else
                                                               tuple(value.values())):
            if isinstance(x, str):
                yield x


def stop_records(app, row, line):
    """(行の記録の種類, 語の記録の種類)。どちらも名前だけ（字は入れない）。"""
    row_kinds, word_kinds = [], []
    try:
        if any(rec.get('row') == row for rec in (getattr(app, '_editor_changes', None) or ())):
            row_kinds.append('選び直しの履歴（メニューの元に戻す）')
    except Exception:
        pass
    try:
        rec = app._autofix_record_for_row(row)
        if rec is not None:
            row_kinds.append('自動反映を手で戻した控え' if rec.get('manual') else '自動反映の控え')
    except Exception:
        pass
    try:
        if line in app._autofix_declined_rows():
            row_kinds.append('断った印（Ctrl+Z で戻した字）')
    except Exception:
        pass
    decisions = getattr(app, 'decisions', None)
    if decisions is not None and line:
        try:
            if any(o and o in line for (o, _c) in (getattr(decisions, '_rejected', None) or {})):
                word_kinds.append('使わない（直しの拒否）')
        except Exception:
            pass
        try:
            if any(w and w in line for w in (getattr(decisions, '_protected', None) or {})):
                word_kinds.append('守る語')
        except Exception:
            pass
        try:
            if any(w and w in line for w in (getattr(decisions, '_odd_only', None) or {})):
                word_kinds.append('紫を下げる語')
        except Exception:
            pass
    choices = getattr(app, 'choices', None)
    if choices is not None and line:
        try:
            for name in ('_contexts', '_units', '_readings'):
                if any(len(x) >= 2 and x in line for x in _str_values(getattr(choices, name, None))):
                    word_kinds.append('選んだ表記の記憶')
                    break
        except Exception:
            pass
    return row_kinds, word_kinds


# --- 行の字（2026-11-21 うにさん: 表にメモ欄の字と、違えば補正欄の字も出す。アプリの画面の中だけ）。見えない字は印にする
# CN_ROW_STATE_TEXT=0 で前の形（字を出さない）
VISIBLE = {'\u3000': '␣', '\t': '[Tab]', '\u00a0': '⟨NBSP⟩', '\u200b': '⟨ゼロ幅⟩',
           '\u200c': '⟨ゼロ幅⟩', '\u200d': '⟨ゼロ幅⟩', '\u2060': '⟨ゼロ幅⟩', '\ufeff': '⟨BOM⟩'}


def text_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_TEXT') != '0'


def visible(text):
    text = text or ''
    body = text.rstrip(' ')
    out = []
    for c in body:
        if c in VISIBLE:
            out.append(VISIBLE[c])
        elif 0xFE00 <= ord(c) <= 0xFE0F:
            out.append('⟨VS⟩')
        else:
            out.append(c)
    return ''.join(out) + '˽' * (len(text) - len(body))


def state2_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_STATE2') != '0'


def _gutter_state(app, row):
    """行番号の右の縦線の見方（app._line_analysis_state）: 'pending'／'incomplete'／'done'／None。"""
    try:
        return app._line_analysis_state(row)
    except Exception:
        return None


COLUMNS_OLD = ('行', '答えと字', '状態', '重い見直し', 'カーソルの行', '統合で後回し', '断った印', '断った語',
               '同じ字の行', '見えない字だけ違う行', '右の欄')


# --- 行に付いている入力の手がかり（2026-11-21 うにさんの報告「140行と142行は同じ字で、どちらも済み・一致なのに、
# 右の欄は 142 だけ直り、140 は書き換えも紫も無い。カーソルは関係ない」）---------------------------------------------
# 同じ字の行で答えが割れるのは、行ごとに補正へ渡す手がかりが違う時（analysis_context.signature: 打った読み〔IME の確定の
# 記録〕・計算・近くの語・上の行の続き）か、答えの出どころが違う時。手がかりの**種類と数だけ**を出す（中身は出さない）。
# CN_ROW_STATE_INPUTS=0 で前の形（この列を出さない）
INPUT_KINDS = (('読み', 1), ('計算', 2), ('近くの語', 0))


def inputs_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_INPUTS') != '0'


def _signature(app, i, lines, result):
    """(近くの語, 打った読み, 計算, 上の行の続き) の組。答えに付いている形（_input_signature・答えを出した時の手がかり）を
    先に、無ければ今の手がかりを作る。分からなければ None。"""
    sig = (result or {}).get('_input_signature')
    if sig is not None:
        return tuple(sig), '答えの時'
    try:
        import analysis_async
        import analysis_context
        import analysis_work_app as input_work
        nearby = tuple(app._nearby_words_for(i))
        readings = tuple(input_work.line_readings(app, i, lines))
        calcs = tuple(input_work.line_calculations(app, i, lines))
        prev = analysis_context.previous_line_of(lines, i)
        return analysis_context.signature(nearby, readings, calcs, prev), '今'
    except Exception:
        return None, ''


def _count(sig, k):
    try:
        return len(sig[k])
    except Exception:
        return 0


# 画面の紫（2026-11-21 05:22Z うにさんの表: 画面に紫があるのに「紫」が 0）。紫は odd_spans（異様の印・show_odd で塗る）と
# unsure_spans（直し方が分からない所）の両方。前は unsure_spans だけを数えていた。CN_ROW_STATE_PURPLE=0 で前の形
def purple_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_PURPLE') != '0'


def purple_spans(result):
    r = result or {}
    if not purple_on():
        return list(r.get('unsure_spans') or ())
    seen, out = set(), []
    for span in list(r.get('odd_spans') or ()) + list(r.get('unsure_spans') or ()):
        try:
            key = (int(span[0]), int(span[1]))
        except Exception:
            continue
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def purple_count(result):
    return len(purple_spans(result))


def purple_reasons(result, show_text):
    """紫の訳（odd_reasons の訳の文）。字を出さない形では位置だけ。"""
    out = []
    for item in (result or {}).get('odd_reasons') or ():
        try:
            a, b = int(item[0]), int(item[1])
        except Exception:
            continue
        why = item[2] if len(item) > 2 and isinstance(item[2], str) else ''
        out.append('%d-%d %s' % (a, b, why) if show_text and why else '%d-%d' % (a, b))
    return ' ／ '.join(out[:4]) or '—'


# 上の行・近くの語・直前の語は、アプリから子へ渡しているが、補正（correction_entry.correct_line）は使わない
# （補正の担当 batch672: CN_PREV_LINE_OFF・CN_NEARBY_WORDS_OFF・CN_RECENT_WORDS_OFF が既定。2026-11-21 05:22Z）
def unused_note(environ=None):
    environ = os.environ if environ is None else environ
    off = [name for name, key in (('上の行', 'CN_PREV_LINE_OFF'), ('近くの語', 'CN_NEARBY_WORDS_OFF'))
           if environ.get(key) != '0']
    return '・' + '／'.join(off) + 'は渡したが補正は使わない' if off else ''


def input_columns(app, i, lines, result, same_rows):
    """手がかりの列（中身は出さない）。same_rows は同じ字の行（1から）。"""
    out = {}
    r = result or {}
    if not r:
        source = '—'
    elif r.get('_from_file') and '_input_signature' not in r:
        source = '控え（ファイル）'
    elif r.get('pending'):
        source = '仮（解析待ち）'
    elif '_input_signature' in r:
        source = '解析（子）'
    else:
        source = '不明'
    out['答えの出どころ'] = source
    sig, when = _signature(app, i, lines, r)
    if sig is None:
        out['手がかり'] = '?'
    else:
        parts = ['%s%d' % (name, _count(sig, k)) for name, k in INPUT_KINDS]
        parts.append('上の行の続き' + ('あり' if len(sig) > 3 else 'なし'))
        out['手がかり'] = '・'.join(parts) + '（%s）' % when + unused_note()
    out['IME の記録'] = _yes(bool(r.get('_ime_evidence')))
    out['紫の訳'] = purple_reasons(r, text_on()) if r else '—'
    out['直し'] = ('あり' if r.get('corrected') not in (None, r.get('original')) else 'なし') if r else '—'
    out['紫'] = str(purple_count(r)) if r else '—'
    status = r.get('analysis_status')
    out['解析の終わり方'] = status if isinstance(status, str) and status and len(status) <= 20 else ('—' if not r else '普通')
    # 同じ字の行と手がかりを比べる（どこが違うか・中身は出さない）
    diffs = []
    results = getattr(app, 'line_results', None) or ()
    for other in same_rows[:SAME_LIMIT]:
        k = other - 1
        o_res = results[k] if 0 <= k < len(results) else None
        o_sig, _w = _signature(app, k, lines, o_res)
        if sig is None or o_sig is None:
            diffs.append('%d: ?' % other)
            continue
        kinds = [name for name, idx in INPUT_KINDS if tuple(sig[idx]) != tuple(o_sig[idx])]
        if (len(sig) > 3) != (len(o_sig) > 3) or (len(sig) > 3 and sig[3] != o_sig[3]):
            kinds.append('上の行')
        o_src = (o_res or {}).get('_from_file') and '_input_signature' not in (o_res or {})
        if bool(o_src) != (source == '控え（ファイル）'):
            kinds.append('出どころ')
        diffs.append('%d: %s' % (other, '同じ' if not kinds else '違う（' + '・'.join(kinds) + '）'))
    out['同じ字の行との違い'] = ', '.join(diffs) or '—'
    return out


INPUT_COLUMNS = ('答えの出どころ', '手がかり', 'IME の記録', '直し', '紫', '紫の訳', '解析の終わり方', '同じ字の行との違い')
COLUMNS = COLUMNS_OLD[:3] + ('縦線',) + COLUMNS_OLD[3:] + ('止める記録',) + INPUT_COLUMNS + ('メモ欄の字', '補正欄の字')


def columns():
    return tuple(c for c in COLUMNS if (c in COLUMNS_OLD or (c == '止める記録' and records_on())
                                        or (c == '縦線' and state2_on())
                                        or (c in INPUT_COLUMNS and inputs_on())
                                        or (c in ('メモ欄の字', '補正欄の字') and text_on())))


def table(app, rows):
    """表の文字（行の中身は入れない）。"""
    lines = app.editor_source_text().split('\n')
    norms = [normalize(t) for t in lines]
    states = [row_state(app, r, lines, norms) for r in rows]
    title = ('行の状態（CorrectNote・メモ欄と補正欄の字を含む・見えない字は ␣ ˽ [Tab] ⟨ゼロ幅⟩ などの印）' if text_on()
             else '行の状態（CorrectNote・字の中身は入れていない）')
    head = [title, '表示: %s' % (
        '統合' if getattr(app, '_layout_is_unified', lambda: False)() else '分割'), '']
    cols = columns()
    body = ['\t'.join(cols)]
    for st in states:
        body.append('\t'.join(str(st.get(c, '')) for c in cols))
    return '\n'.join(head + body)


# --- この行を比べて解く（2026-11-21 補正担当の依頼: 誤判定タブ20行は、雲で今の補正ファイルと PC の IME 記録を通すと
# 書き換えも紫も出ない。違いはアプリ側の材料〔本人の学習・決めた語・上下の行の語〕だけ）。選んだ1行を、使い捨ての子で
# 次の通りにエンジンへ通し、結果を並べる。表の答え・控え・保存は変えない（比べるだけ）。子は終わったら閉じる。
#   今のまま／上下の行の語なし（nearby_words・recent_words を空に。CN_NEARBY_MARK=0 と同じ材料）／
#   学習・決めた語なし（語彙・決めた語〔使わない・守る〕・選んだ表記を空に）／両方なし
# 子へ送る求めは1つずつ（子は新しい求めが来ると前の求めを捨てる）。CN_ROW_STATE_COMPARE=0 でボタンを出さない
COMPARE_VARIANTS_OLD = (('今のまま', False, False, False), ('上下の行の語なし', True, False, False),
                        ('学習・決めた語なし', False, True, False), ('両方なし', True, True, False))
# 上の行の続き（previous_line）を渡さない通りを足した（2026-11-21 うにさんの表: 直らない・誤って直る行〔誤判定20・変換140〕は
# どちらも「上の行の続きあり」、直る行〔21・142〕は「続きなし」）。(名前, 上下の行の語なし, 学習なし, 上の行の続きなし)。
# CN_ROW_STATE_COMPARE_PREV=0 で前の4通り
COMPARE_VARIANTS = (('今のまま', False, False, False), ('上の行の続きなし', False, False, True),
                    ('上下の行の語なし', True, False, False), ('上の行の続きも上下の語もなし', True, False, True),
                    ('学習・決めた語なし', False, True, False))


def compare_variants(environ=None):
    environ = os.environ if environ is None else environ
    return COMPARE_VARIANTS_OLD if environ.get('CN_ROW_STATE_COMPARE_PREV') == '0' else COMPARE_VARIANTS
COMPARE_TIMEOUT_S = 240.0


def compare_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_ROW_STATE_COMPARE') != '0'


def empty_learning(state):
    """子へ送る材料から、本人の学習（語彙）・決めた語・選んだ表記を外した写し（元は変えない）。"""
    out = dict(state)
    out['entries'] = []
    out['revision'] = -1
    out['decisions'] = {name: {} for name in (state.get('decisions') or {})}
    out['choices'] = {name: {} for name in (state.get('choices') or {})}
    out['choice_revision'] = -1
    out.pop('_state_identity', None)
    return out


def compare_tasks(app, i):
    """比べる4通りの (名前, 求め, 学習を外すか)。"""
    import analysis_async
    lines = list(getattr(app, '_prev_lines', None) or [])
    if not 0 <= i < len(lines):
        raise ValueError('row out of range')
    results = getattr(app, 'line_results', None) or ()
    res = results[i] if i < len(results) else None
    base = analysis_async.line_task(app, i, res, False)
    base['defer_heavy'] = False
    out = []
    for name, no_near, no_learn, no_prev in compare_variants():
        task = dict(base)
        if no_near:
            task['nearby'] = ()
            task['recent'] = ()
        if no_prev:
            task['previous_line'] = None
        out.append((name, task, no_learn))
    return out


def summarize(line, value):
    """子の答え → (書き換え, 紫の数, 直した字)。"""
    result = (value or {}).get('result') if isinstance(value, dict) else None
    if not isinstance(result, dict):
        return ('?', '?', '')
    corrected = result.get('corrected')
    changed = corrected is not None and corrected != line
    purple = purple_count(result)
    return ('あり' if changed else 'なし', str(purple), corrected if changed else '')


class Compare:
    """使い捨ての子で1行を4通りに解く。done(rows) を本体の手で呼ぶ（rows: [(名前, 書き換え, 紫, 直した字)]）。"""

    def __init__(self, app, row, done, worker_factory=None):
        self.app, self.row, self.done = app, row, done
        self.worker_factory = worker_factory
        self.worker = None
        self.rows = []
        self.todo = []
        self.current = None
        self.started = 0.0
        self.line = ''
        self.closed = False

    def start(self):
        import time
        import analysis_worker
        app = self.app
        i = self.row - 1
        self.line = (getattr(app, '_prev_lines', None) or [''])[i] if 0 <= i < len(getattr(app, '_prev_lines', None) or ()) else ''
        self.todo = compare_tasks(app, i)
        state = analysis_worker.snapshot(app)
        self.states = {False: state, True: empty_learning(state)}
        self.sent_learn = None
        self.worker = (self.worker_factory or analysis_worker.Worker)()
        self.started = time.monotonic()
        self._next()

    def _next(self):
        import time
        if not self.todo:
            self._finish()
            return
        name, task, no_learn = self.todo.pop(0)
        state = self.states[no_learn] if self.sent_learn is not no_learn else None
        self.sent_learn = no_learn
        self.current = (name, self.worker.submit(task, state), time.monotonic())
        self._schedule()

    def _schedule(self):
        try:
            self.app.root.after(200, self._tick)
        except Exception:
            self._finish()

    def _tick(self):
        import time
        if self.closed:
            return
        name, ident, since = self.current
        try:
            value = self.worker.poll(ident)
        except Exception as error:
            self.rows.append((name, 'エラー', type(error).__name__, ''))
            self._finish()
            return
        if value is None:
            if time.monotonic() - since > COMPARE_TIMEOUT_S:
                self.rows.append((name, '時間切れ', '', ''))
                self._finish()
                return
            self._schedule()
            return
        self.rows.append((name,) + summarize(self.line, value))
        self._next()

    def _finish(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.worker is not None:
                self.worker.close()
        except Exception:
            pass
        try:
            self.done(self.rows)
        except Exception:
            pass


def compare_text(row, rows, show_text=True):
    head = ['この行を比べて解く（%d行目・表の答えや保存は変えていない）' % row, '',
            chr(9).join(('材料', '書き換え', '紫', '直した字') if show_text else ('材料', '書き換え', '紫'))]
    for name, changed, purple, corrected in rows:
        cells = [name, changed, purple] + ([visible(corrected) if corrected else '—'] if show_text else [])
        head.append(chr(9).join(cells))
    return chr(10).join(head)


def open_window(app, colors=None):
    import tkinter as tk
    colors = dict(colors or {})
    bg = colors.get('bg', '#f6f4ee')
    ink = colors.get('ink', '#1c2b2d')
    panel = colors.get('panel', bg)
    dlg = tk.Toplevel(app.root)
    dlg.title('行の状態')
    dlg.configure(bg=bg)
    place = getattr(app, '_place_dialog', None)
    if place is not None:
        try:
            place(dlg, 980, 360)
        except Exception:
            pass
    top = tk.Frame(dlg, bg=bg)
    top.pack(fill='x', padx=8, pady=6)
    tk.Label(top, text='行番号（例: 140, 142, 20-21）:', bg=bg, fg=ink).pack(side='left')
    entry = tk.Entry(top, width=30, bg=panel, fg=ink, insertbackground=ink)
    entry.pack(side='left', padx=6)
    entry.insert(0, default_text(app))
    text = tk.Text(dlg, bg=panel, fg=ink, wrap='none', font=('Consolas', 9), height=14)
    try:      # 表の字（メモ欄・補正欄の字）の絵文字を色付きで（emoji_widgets・2026-11-21 うにさん）
        import emoji_widgets
        emoji_widgets.text(text)
    except Exception:
        pass

    def show(_e=None):
        try:
            last = len(app.editor_source_text().split('\n'))
        except Exception:
            last = 1
        rows = parse_rows(entry.get(), last) or default_rows_for(app, last)
        text.configure(state='normal')
        text.delete('1.0', 'end')
        text.insert('1.0', table(app, rows))
        text.configure(state='disabled')
        return 'break'

    def copy():
        try:
            dlg.clipboard_clear()
            dlg.clipboard_append(text.get('1.0', 'end-1c'))
        except Exception:
            pass
    tk.Button(top, text='表を作る', command=show).pack(side='left')
    tk.Button(top, text='表をコピー', command=copy).pack(side='left', padx=6)
    state = {'job': None}

    def compare():
        # 行番号の欄の最初の行を、使い捨ての子で4通りに解いて、表の下に足す（比べるだけ・Compare）
        if state['job'] is not None and not state['job'].closed:
            return
        try:
            last = len(app.editor_source_text().split(chr(10)))
        except Exception:
            last = 1
        rows = parse_rows(entry.get(), last) or default_rows_for(app, last)
        row = rows[0]

        def put(message):
            try:
                text.configure(state='normal')
                text.insert('end', chr(10) + chr(10) + message)
                text.configure(state='disabled')
                text.see('end')
            except Exception:
                pass

        def done(results):
            put(compare_text(row, results, text_on()))
        put('この行を比べて解く（%d行目）: 子を起こして比べています。1〜数分かかります…' % row)
        job = state['job'] = Compare(app, row, done)
        try:
            job.start()
        except Exception as error:
            put('比べられませんでした: %s' % type(error).__name__)
            job.closed = True
    if compare_on():
        tk.Button(top, text='この行を比べて解く', command=compare).pack(side='left', padx=6)

    def closing(event):
        # 窓を閉じたら、比べている子も閉じる（答えは捨てる）
        job = state['job']
        if event.widget is dlg and job is not None and not job.closed:
            job.done = lambda rows: None
            job._finish()
    dlg.bind('<Destroy>', closing, add='+')
    text.pack(fill='both', expand=True, padx=8, pady=(0, 8))
    entry.bind('<Return>', show)
    dlg.bind('<Escape>', lambda e: dlg.destroy())
    dlg._row_state = dict(entry=entry, text=text, show=show, copy=copy, compare=compare, compare_state=state)
    show()
    return dlg
