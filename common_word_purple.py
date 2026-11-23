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
import re

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


_AFTER_NOUN = frozenset('をがにはもでとだの')


def _rows(face):
    try:
        from morphology import dictionary_inflections
        return [str(r[0]) for r in dictionary_inflections(face) or ()]
    except Exception:
        return []


def time_head_text(text, after):
    """時の名詞（今・昔・間: 辞書に 名詞,副詞可能 の行がある身近な語）＋身近な名詞（お・ご は除いて見る）に
    ちょうど分けられ、すぐ後ろが助詞か だ（今｜本を・昔｜煙を・間｜お風呂に）。時の名詞は助詞を挟まずに後ろの
    名詞句に続くのがふつうなので、打ち違いの跡とはみない（2026-11-20 正しい文の見直し）。
    CN_COMMON_WORD_TIME_HEAD=0 で見ない。"""
    if os.environ.get('CN_COMMON_WORD_TIME_HEAD') == '0' or not after or after not in _AFTER_NOUN:
        return False
    if len(text) < 2 or not all(_jp(c) for c in text):
        return False
    for i in range(1, len(text)):
        head, rest = text[:i], text[i:]
        if not any(r.startswith('名詞,副詞可能') for r in _rows(head)) or _rank(head) >= PART:
            continue
        core = rest[1:] if len(rest) > 1 and rest[0] in 'おご' else rest
        if not any('一' <= c <= '鿿' for c in core):
            continue
        if any(r.startswith(('名詞,一般', '名詞,形容動詞語幹', '名詞,サ変接続')) for r in _rows(core)) \
                and _rank(core) < COMMON:
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
                and not _kanji_at(line, a - 1) and not _kanji_at(line, b)
                and (common_text(line[a:b]) or time_head_text(line[a:b], line[b:b + 1]))):
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


_KATA_TE = re.compile('「って」と「[^」]+」は続けて置けない')


def _kata(c):
    return 'ァ' <= c <= 'ヺ' or c == 'ー'


def drop_kata_te(line, result):
    """片仮名の語＋って（メモって・ググって: 片仮名の語に る を付けた話し言葉の動詞の て の形）の後ろの語との
    つながりの紫は外す。紫がほかの紫とつながっていれば、残りの理由の所まで狭める（2026-11-20 挙動関連担当: 簡易入力の
    試験 メモってから資料｜乳力 の紫が頭の メモって まで掛かっていた）。CN_COMMON_WORD_KATA_TE=0 で前のまま。"""
    if os.environ.get('CN_COMMON_WORD_KATA_TE') == '0' or not isinstance(result, dict):
        return result
    reasons = [r for r in result.get('odd_reasons') or () if isinstance(r, (list, tuple)) and len(r) >= 3]
    bad = [r for r in reasons if _KATA_TE.search(str(r[2])) and line[r[0]:r[0] + 2] == 'って'
           and r[0] >= 2 and _kata(line[r[0] - 1]) and _kata(line[r[0] - 2])]
    if not bad:
        return result
    rest = [r for r in reasons if r not in bad]
    new_odd = []
    for x in result.get('odd_spans') or ():
        a, b = x[0], x[1]
        if not any(a <= r[0] and r[1] <= b for r in bad):
            new_odd.append(x)
            continue
        inner = [r for r in rest if a <= r[0] and r[1] <= b and (r[0], r[1]) != (a, b)]
        if inner:
            new_odd.append((min(r[0] for r in inner), max(r[1] for r in inner)))
    out = dict(result)
    out['odd_spans'] = new_odd
    keep = set((x[0], x[1]) for x in new_odd)
    out['odd_reasons'] = [r for r in rest if any(a <= r[0] and r[1] <= b for a, b in keep)]
    for a, b in keep:
        if not any((r[0], r[1]) == (a, b) for r in out['odd_reasons']):
            whole = [r for r in rest if r[0] <= a and b <= r[1]]
            if whole:
                out['odd_reasons'].append((a, b) + tuple(whole[0][2:]))
    return out


def drop_kata_ru(line, result):
    """知られた片仮名の語＋っ・ら・り・る・れ・ろ（ミスった・バズる: 片仮名の語に る を付けた話し言葉の動詞）の、
    片仮名の語の中だけに掛かる紫は外す（2026-11-20 正しい文の見直し: 彼がミスったんだ の ミ）。
    CN_COMMON_WORD_KATA_RU=0 で前のまま。"""
    if os.environ.get('CN_COMMON_WORD_KATA_RU') == '0' or not isinstance(result, dict):
        return result
    odd = list(result.get('odd_spans') or ())
    if not odd or (result.get('corrected') or line) != line:
        return result
    runs = []
    for m in re.finditer('[ァ-ヺー]{2,}', line):
        if line[m.end():m.end() + 1] and line[m.end()] in 'っらりるれろ':
            try:
                from morphology import tokenize
                tk = list(tokenize(m.group()))
            except Exception:
                return result
            if len(tk) == 1 and tk[0].pos == '名詞' and tk[0].has_reading and tk[0].pos_sub != '固有名詞':
                runs.append((m.start(), m.end() + 1))
    if not runs:
        return result
    keep = [x for x in odd if not any(a <= x[0] and x[1] <= b for a, b in runs)]
    if len(keep) == len(odd):
        return result
    out = dict(result)
    out['odd_spans'] = keep
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or ()
                          if not (len(r) >= 2 and any(a <= r[0] and r[1] <= b for a, b in runs))]
    return out


def drop_prohibit_quote(line, result):
    """動詞の言い切り＋な（禁止）＋と・って（引用）にちょうど掛かる、弱い理由だけの紫は外す（開けるなと言った）。
    （2026-11-20 正しい文の見直し）。CN_COMMON_WORD_PROHIBIT=0 で前のまま。"""
    if os.environ.get('CN_COMMON_WORD_PROHIBIT') == '0' or not isinstance(result, dict):
        return result
    odd = list(result.get('odd_spans') or ())
    if not odd or (result.get('corrected') or line) != line:
        return result
    try:
        import odd_reason_fill as F
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    gone = []
    for x in odd:
        a, b = x[0], x[1]
        why = [str(r[2]) for r in result.get('odd_reasons') or () if len(r) >= 3 and r[0] < b and a < r[1]]
        if not F._all_weak(why):
            continue
        hit = [t for t in toks if t.start < b and a < t.end]
        if (len(hit) == 3 and hit[0].start == a and hit[-1].end == b and hit[0].pos == '動詞'
                and hit[0].infl_form == '基本形' and hit[1].surface == 'な' and hit[1].pos == '助詞'
                and hit[2].surface in ('と', 'って') and hit[2].pos == '助詞'):
            gone.append((a, b))
    if not gone:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in odd if (x[0], x[1]) not in gone]
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or () if not any(r[0] < b and a < r[1] for a, b in gone)]
    return out


def correct_line(line, *a, **k):
    return drop_kata_ru(line, drop_prohibit_quote(line, drop_common(line, drop_kata_te(line, _orig['correct_line'](line, *a, **k)))))


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
