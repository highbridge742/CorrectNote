# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""入口が「異様だが直し先を決められない」とだけ見た紫が、身近な語そのもの（中元）か、身近な2語の続き（月末｜締め）に
掛かっているなら、その紫を外す（2026-11-13 補正担当、全体評価の作った正しい文: お中元・月末締め に紫）。

入口の解析は語の区切りを 月｜末締め のように切ることがあり、切った片方が珍しい語に見えると紫になる。紫の所の字が、
表に1語として在る身近な語か、身近な2語にちょうど分けられるなら、打ち違いの跡とはみない。
- 紫の理由が無いか、決め手の無い理由（_GENERIC）のときだけ。理由の付いた紫（意味の組・打ち違いの跡など）は外さない。
- 紫の所に直しが掛かっていないこと。字は漢字・かなだけ。
- 紫の両隣が漢字でないこと（流布｜委書類 のように漢字の続きの途中で切れた紫は、続きごと怪しいので外さない）。
correction_entry.correct_line を外から包む。CN_COMMON_WORD_PURPLE=0 で前のまま。
"""
import difflib
import os

COMMON = 600       # 1語のときの身近さ（ime_reconvert._rank がこれ未満）
PART = 560         # 2語に分けるときの、それぞれの身近さ
_GENERIC = ('', '異様だと見たが、直し先を決められなかった')
_orig = {}


def _rank(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face)
    except Exception:
        return 800


def _unit(face):
    try:
        import seed_japanese
        return seed_japanese.is_unit(face) is True
    except Exception:
        return False


def _jp(c):
    return '一' <= c <= '鿿' or 'ぁ' <= c <= 'ゖ' or c == '々'


def _kanji_at(line, i):
    return 0 <= i < len(line) and ('一' <= line[i] <= '鿿' or line[i] == '々')


def common_text(text):
    """身近な1語か、身近な2語にちょうど分けられるか。"""
    if len(text) < 2 or not all(_jp(c) for c in text) or not any('一' <= c <= '鿿' for c in text):
        return False
    if _unit(text) and _rank(text) < COMMON:
        return True
    for i in range(1, len(text)):
        a, b = text[:i], text[i:]
        if len(a) >= 2 and len(b) >= 2 and _unit(a) and _unit(b) and _rank(a) < PART and _rank(b) < PART:
            return True
    return False


def drop_common(line, result):
    if os.environ.get('CN_COMMON_WORD_PURPLE') == '0' or not isinstance(result, dict):
        return result
    odd = list(result.get('odd_spans') or ())
    if not odd:
        return result
    got = result.get('corrected') or line
    changed = [(o[1], o[2]) for o in difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    reasons = {}
    for r in result.get('odd_reasons') or ():
        try:
            reasons.setdefault((r[0], r[1]), []).append(r[2] if len(r) > 2 else '')
        except Exception:
            pass
    keep, gone = [], []
    for x in odd:
        a, b = x[0], x[1]
        why = reasons.get((a, b), [''])
        if (all(w in _GENERIC for w in why) and not any(s < b and a < e for s, e in changed)
                and not _kanji_at(line, a - 1) and not _kanji_at(line, b) and common_text(line[a:b])):
            gone.append((a, b))
        else:
            keep.append(x)
    if not gone:
        return result
    out = dict(result)
    out['odd_spans'] = keep
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or ()
                          if not (isinstance(r, (list, tuple)) and (r[0], r[1]) in gone)]
    return out


def correct_line(line, *a, **k):
    return drop_common(line, _orig['correct_line'](line, *a, **k))


def install():
    if _orig or os.environ.get('CN_COMMON_WORD_PURPLE') == '0':
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    # 包みの外から元の引数（defer_heavy・tab_has_kana など）が見えるように（analysis_worker が inspect.signature で見る・2026-11-13）
    import functools
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True
