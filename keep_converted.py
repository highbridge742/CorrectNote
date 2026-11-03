# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""打ち違いの直しのついでに、打ち違いの無い語の表記まで替えた所を元に戻す（keep_converted・手分け C・2026-11-01）。

1行に打ち違いがあると、前の段は行の読みから変換し直すことがあり、そのとき打ち違いの無い語まで
同じ読みの別の表記（漢字の語 → かな・別の漢字の語）になることがある。
  漢字を含む語を読みの同じ別の表記（ひらがな・別の漢字の語）に替えた所は、同じ行で読みの変わる直し（打ち違いの直し）が
  別の所にあり、そこと続いていないときだけ元の表記に戻す。読みの同じ語だけを替える直し（IME の選び違いの直し）や、
  打ち違いの直しと続いている所（変換の区切りごと崩れた所）は戻さない。
特定の語は見ない。読みが同じかどうかと、直しの位置だけで決める。
"""
import difflib

_PLAIN_LABELS = ('かな入力', 'ローマ字入力', 'ローマ字', 'romaji')


def _reading(text):
    import morphology
    out = []
    for t in morphology.tokenize(text):
        r = t.reading if getattr(t, 'has_reading', True) and t.reading else t.surface
        out.append(_hira(r))
    return ''.join(out)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _has_kanji(s):
    return any('一' <= c <= '鿿' or c == '々' for c in s)


def _all_hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゟ' for c in s)


def _word_spans(text):
    import morphology
    return [(t.start, t.end) for t in morphology.tokenize(text)]


def _segments(line, done):
    """元の行の語の切れ目に広げた (i1, i2, j1, j2) の並び（直した所だけ）。"""
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()]
    bounds = sorted({0, len(line)} | {a for a, b in _word_spans(line)} | {b for a, b in _word_spans(line)})
    segs = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            continue
        a = max(x for x in bounds if x <= i1)
        b = min(x for x in bounds if x >= i2) if i2 > i1 else min(x for x in bounds if x >= i1)
        segs.append([a, b, j1 - (i1 - a), j2 + (b - i2)])
    merged = []
    for s in segs:
        if merged and s[0] < merged[-1][1]:
            merged[-1] = [merged[-1][0], max(s[1], merged[-1][1]), merged[-1][2], max(s[3], merged[-1][3])]
        else:
            merged.append(s)
    return [tuple(x) for x in merged if 0 <= x[2] <= x[3] <= len(done)]


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        segs = _segments(line, done)
        info = []
        for i1, i2, j1, j2 in segs:
            a, b = line[i1:i2], done[j1:j2]
            same = bool(a) and bool(b) and _reading(a) == _reading(b)
            info.append((i1, i2, j1, j2, a, b, same))
    except Exception:
        return result
    reading_fix = [(i1, i2) for i1, i2, j1, j2, a, b, same in info if not same]
    # 選び違いを直す段（語の組 など）が名指しで替えた所は戻さない。行の読みからの変換し直し（かな入力）のついでの所だけ
    chosen = [(str(d[0]), str(d[1])) for d in (result.get('details') or ())
              if isinstance(d, (list, tuple)) and len(d) >= 3 and d[2] not in _PLAIN_LABELS]
    back = []
    for i1, i2, j1, j2, a, b, same in info:
        if not same or not _has_kanji(a):
            continue
        if any(x < i2 and i1 < y for x, y in decided or ()):
            continue
        if any(da and db and (da in a or a in da) and (db in b or b in db) for da, db in chosen):
            continue
        if reading_fix and not any(x <= i2 and i1 <= y for x, y in reading_fix) and (_all_hira(b) or _has_kanji(b)):
            back.append((i1, i2, j1, j2, a, b))
    if not back:
        return result
    new = done
    for i1, i2, j1, j2, a, b in sorted(back, key=lambda x: -x[2]):
        new = new[:j1] + a + new[j2:]
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': new, 'changed': new != line,
                'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
    if result.get('details'):
        gone = {b for *_x, a, b in back}
        out['details'] = [d for d in result['details'] if not (isinstance(d, (list, tuple)) and len(d) >= 2 and d[1] in gone)]
    return out
