# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""ファイルタブの名前（2026-11-16 うにさんの指定）。決まりだけ（画面は使わない）。

1. タイトルが入っていれば、タイトルの字。
2. タイトルが空なら、ファイル名＋拡張子。
3. 拡張子を除いたファイル名とタイトルが同じなら、ファイル名＋拡張子。
4. ただし拡張子が .txt なら（大文字小文字は問わない）拡張子は出さない。
5. まだ保存していない（ファイル名の無い）タブは今の名前のまま（fallback）。
CN_TAB_LABEL_TITLE=0 で前の名前（fallback）。

全部のタブが窓に収まらない時だけ、名前を字の幅で切る（全角＝2・半角＝1。末尾に「…」は付けない）。いちばん短くても
幅 MIN_WIDTH（既定 12＝全角6字・半角だけなら12字）。MIN_WIDTH はデバッグのパラメータで変えられる（debug_menu）。
"""
import os
import unicodedata

MIN_WIDTH = 12          # 切る時の、いちばん短い幅（全角6字・半角12字・2026-11-16 うにさん）
MIN_WIDTH_MAX = 40      # デバッグのパラメータの上限


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_TAB_LABEL_TITLE') != '0'


def _one_line(text):
    return ' '.join(str(text or '').split())


def display_name(path, doc_title, fallback, environ=None):
    """タブに出す名前（切る前の全体）。path: 保存したファイルの道（無ければ未保存）。"""
    if not enabled(environ) or not path:
        return fallback
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    file_name = stem if ext.lower() == '.txt' else base
    title = _one_line(doc_title)
    if not title or title == stem:
        return file_name
    return title


def char_width(ch):
    """字の幅: 全角（東アジアの広い字・全角）は2、ほかは1。"""
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1


def text_width(text):
    return sum(char_width(c) for c in text)


def shorten(name, limit):
    """幅 limit を超える分を切る（「…」は付けない）。limit が None なら切らない。"""
    if limit is None or text_width(name) <= limit:
        return name
    out, used = [], 0
    for ch in name:
        w = char_width(ch)
        if used + w > limit:
            break
        out.append(ch)
        used += w
    return ''.join(out)


def fit_limit(names, width_of, available, min_width=None):
    """すべてのタブが available に収まる、いちばん大きい幅の上限。切らずに収まれば None。
    width_of(names_shown) → 帯の幅（画素）。下げても収まらなければ min_width（それより下げない）。"""
    min_width = MIN_WIDTH if min_width is None else min_width
    if not names or width_of(list(names)) <= available:
        return None
    widest = max(text_width(n) for n in names)
    for limit in range(widest - 1, min_width - 1, -1):
        if width_of([shorten(n, limit) for n in names]) <= available:
            return limit
    return min_width
