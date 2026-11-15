# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""かなのままの1字の和語の名詞＋格助詞で始まる文（作った例: きをうえる。てをふる。はをみがく。）を、打ったまま通す
（2026-11-14 補正担当・全体評価の方針 U）。

なぜ
----
行の頭（か句読点・空白の後ろ）のひらがな1字に1字の助詞が続く所を、かな入力の戻しや助詞の並びの見立てが
打ち違いの切れ端とみて、別の読みに戻して語を作り直す（きをうえる → きょうえる）か、紫を付ける。けれども、その1字が
辞書で身近な1字の名詞の読み（木・手・歯・目・日・火・絵）で、助詞の後ろが用言で文が成り立つなら、打ったままで正しい。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
1. 元の行を句読点・空白で区切り、区切りの頭が「ひらがな1字＋格助詞・係助詞1字」で、その1字の読みの1字の漢字の名詞が
   辞書（reading_lattice の表）に在り身近（ime_reconvert._rank が COMMON 以下）なものを探す。
2. 助詞の後ろの区切りの残りを解析し、頭が動詞・形容詞で、その後ろが助動詞・助詞・記号だけなら、その区切りは
   打ったままで文が成り立つ（かなの行の費用は和語のかなで高く出るので、費用では見ない）。
3. その区切りに掛かる書き換え（同じ読みの漢字に置いただけの所は除く）を元に戻し、区切りの中の紫を外す。
特定の語や文字列には合わせない。切り替え: CN_LONE_KANA_HEAD=0 で前のまま。
"""
import difflib
import functools
import os

COMMON = 530
_PARTICLES = 'をがにではもへと'
_CUT = '、。，．,.!?！？「」『』（）() 　\t'
_orig = {}


def _on():
    return os.environ.get('CN_LONE_KANA_HEAD') != '0'


def _hira(c):
    return 'ぁ' <= c <= 'ゖ'


def _noun_reading(c):
    try:
        import reading_lattice as lat
        import ime_reconvert as R
        lat.load()
        return any(p == '名詞' and len(f) == 1 and '一' <= f <= '鿿' and R._rank(f) <= COMMON
                   for f, _l, _r, _c, p in lat._table.get(c, ()))
    except Exception:
        return False


def _predicate(rest):
    """rest（助詞の後ろ、区切りの終わりまで）が 用言＋助動詞・助詞 だけか"""
    if not rest:
        return False
    try:
        from morphology import tokenize
        toks = [t for t in tokenize(rest)]
    except Exception:
        return False
    if not toks or toks[0].pos not in ('動詞', '形容詞'):
        return False
    # 用言は1つだけ（後ろは補助の動詞・助動詞・助詞・記号）。用言が並ぶ長い残りは、語の切り方が当てにならない
    return all(t.pos in ('助動詞', '助詞', '記号') or (t.pos == '動詞' and (t.pos_sub or '').startswith('非自立'))
               for t in toks[1:])


def _head_alone(seg):
    """区切りを解析した頭の語が、その1字だけか（おとうとが の お は おとうと の頭で、1字の名詞ではない）"""
    try:
        from morphology import tokenize
        toks = list(tokenize(seg))
    except Exception:
        return False
    return bool(toks) and toks[0].end == 1 and len(toks) > 1 and toks[1].end == 2


def spans(line):
    """打ったままで成り立つ区切り [(始め, 終わり)]（元の行の位置）"""
    out = []
    i = 0
    n = len(line)
    while i < n:
        j = i
        while j < n and line[j] not in _CUT:
            j += 1
        seg = line[i:j]
        if (len(seg) >= 3 and (i == 0 or line[i - 1] not in '）)」』') and _hira(seg[0]) and seg[1] in _PARTICLES and _noun_reading(seg[0])
                and _predicate(seg[2:]) and _head_alone(seg)):
            out.append((i, j))
        i = j + 1
    return out


def _same_reading(src, dst):
    try:
        from morphology import tokenize
        got = ''.join(t.reading if t.reading and t.reading != '*' else t.surface for t in tokenize(dst))
        return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in got) == src
    except Exception:
        return False


def keep(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    sp = spans(line)
    if not sp:
        return result
    text = result.get('corrected') or line
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    new = []
    for tag, i1, i2, j1, j2 in ops:
        piece = text[j1:j2]
        if tag != 'equal' and any(a <= i1 and i2 <= b for a, b in sp) and not (
                all(_hira(c) for c in line[i1:i2]) and _same_reading(line[i1:i2], piece)):
            piece = line[i1:i2]
        new.append(piece)
    new = ''.join(new)

    def outside(x):
        return not any(a <= x[0] and x[1] <= b + 1 for a, b in sp)
    odd = [x for x in result.get('odd_spans') or () if outside(x)]
    why = [r for r in result.get('odd_reasons') or () if outside(r)]
    if new == text and len(odd) == len(result.get('odd_spans') or ()) and len(why) == len(result.get('odd_reasons') or ()):
        return result
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2], 'odd_spans': odd, 'odd_reasons': why})
    if new != text:
        out['details'] = [d for d in result.get('details') or ()
                          if not (isinstance(d, (list, tuple)) and len(d) >= 2 and isinstance(d[1], str)
                                  and d[1] and d[1] not in new)]
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
