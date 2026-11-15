# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""入口が理由なしで付けた「珍しい辞書の語」の紫を、IME の第1候補で見直す（2026-11-15 全体評価の方針、既定オフ）。

なぜ
----
打鍵・焙煎 のような辞書の語でも、珍しいと入口（corrector）が理由なしの紫を付ける。辞書に在るだけでは、
会議の死霊（資料）のような同音の選び違いと見分けが付かない。見分ける手がかりは IME に在る: その語の読みを
IME で変換した第1候補が今の表記と同じなら、書き手が IME の選び違いをした見込みは低い。第1候補が別の表記
（しりょう → 資料）なら選び違いの見込みが残るので紫のまま。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を包む（functools.update_wrapper あり）。
1. 書き換えの無い行で、理由の文が1つも付いていない紫だけを見る（odd_reason_fill が一般の理由を付ける前。
   install は odd_reason_fill より先に呼ぶので内側に入る）。
2. 紫の中の自立語がどれも漢字を含む辞書の語（かなだけの語は見ない）なら、それぞれの読みを IME に変換で聞く
   （読み取りだけ・確定もキー入力もしない）。行あたり MAX_ASK 回まで。
3. どの語も第1候補が今の表記と同じなら紫を外す。
IME が無い（雲）・使えない時は何もしない。切り替え: CN_IME_FIRST_KEEP=1 で入る（既定オフ）。
"""
import functools
import os

MAX_ASK = 3
_orig = {}
_memo = {}


def _on():
    return os.environ.get('CN_IME_FIRST_KEEP') == '1'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (s or ''))


def _first(reading):
    if reading in _memo:
        return _memo[reading]
    got = None
    try:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if getattr(ime, 'available', False):
                got = ime.convert(reading) or None
    except Exception:
        got = None
    if len(_memo) > 2000:
        _memo.clear()
    _memo[reading] = got
    return got


def keep(line, result, ask=None):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line or not result.get('odd_spans'):
        return result
    try:
        import odd_reason_fill as F
        from morphology import tokenize
    except Exception:
        return result
    ask = ask or _first
    reasons = [r for r in result.get('odd_reasons') or () if len(r) >= 3]
    toks = list(tokenize(line))
    left = MAX_ASK
    drop = set()
    for x in result['odd_spans']:
        a, b = x[0], x[1]
        texts = [r[2] for r in reasons if r[0] < b and a < r[1]]
        # 理由の文が1つも付いていない紫だけ（入口が理由なしで付けたもの）。odd_reason_fill が理由を付ける前に見るので、
        # この段は odd_reason_fill の内側に入れる。「辞書で確かめられません」など理由の付いた紫は触らない（2026-11-15 全体評価:
        # 理由の付いた紫で見ると short2 の打ち違い2行の紫を失った）
        if texts:
            continue
        inside = [t for t in toks if t.start < b and a < t.end]
        words = [t for t in inside if t.pos in ('名詞', '動詞', '形容詞', '副詞')]
        if not words or any(t.start < a or t.end > b for t in words):
            continue
        if not all(any(_kanji(c) for c in t.surface) and t.reading and F._dict_entries(t.surface) for t in words):
            continue
        if len(words) > left:
            continue
        ok = True
        for t in words:
            left -= 1
            if ask(_hira(t.reading)) != t.surface:
                ok = False
                break
        if ok:
            drop.add((a, b))
    if not drop:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result['odd_spans'] if (x[0], x[1]) not in drop]
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or () if not (len(r) >= 2 and (r[0], r[1]) in drop)]
    if 'unsure_spans' in result:
        out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if (x[0], x[1]) not in drop]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        return keep(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
