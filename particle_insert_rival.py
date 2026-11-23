# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""助詞を1字足しただけの直しに、隣のキーの打ち違いの読みで届く身近な語を比べる
（2026-11-23 補正担当、うに 誤判定タブ: 漢字に変換された打ち違いが「ナ形容詞の語幹＋に＋動詞」の助詞の脱字と
見られ、本当の語に届かなかった）。

なぜ
----
解析が「ナ形容詞の語幹＋動詞」（静か｜歩く）の間に に を足す直しは、漢字に変換された打ち違いの塊にも
当たる。塊の読みを隣のキー（同じ段の左右・同じ指の上下）で1〜2字替えると、語彙の身近な語の読みに
ちょうど届き、そう替えた行が助詞を足さずに読めるなら、打ち違いの見立ての方が筋が通る。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
答えの直しが「助詞1字を足しただけ」の1つのときだけ見る。足した所の前の語と後ろの漢字の並びを1つの塊とし、
その読み（kanji_guess.reading_combos）を隣のキーで1〜2字替えた読みのうち、語彙に在る漢字の語で、一般の文章で
身近な語（ime_reconvert の順位が SAFE_RANK 以下）がちょうど1つなら、その語に替えた行を解析し直す。
替えた行の語が1語に読め、読めない語が無ければ採る。決まらなければ元の答えのまま。
切り替え: CN_PARTICLE_INSERT_RIVAL=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}
SAFE_RANK = 3000
MAX_KEY = 1.05
_PARTICLES = set('にでをがはとへも')


def _on():
    return os.environ.get('CN_PARTICLE_INSERT_RIVAL') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(c):
    return 'ぁ' <= c <= 'ゖ'


_NEIGH = {}


def _neighbors(c):
    got = _NEIGH.get(c)
    if got is None:
        import kana_layout as kl
        got = []
        for o in range(ord('ぁ'), ord('ゖ') + 1):
            x = chr(o)
            if x != c and kl.kana_key_distance(c, x) <= MAX_KEY:
                got.append(x)
        _NEIGH[c] = got
    return got


def _variants(r):
    """r を隣のキーで1〜2字替えた読み"""
    out = set()
    for i, c in enumerate(r):
        for x in _neighbors(c):
            a = r[:i] + x + r[i + 1:]
            out.add(a)
            for j in range(i + 1, len(r)):
                for y in _neighbors(r[j]):
                    out.add(a[:j] + y + a[j + 1:])
    return out


def _inserted(line, done):
    """答えが line に助詞1字を足しただけなら、足した位置（line の中）"""
    if len(done) != len(line) + 1:
        return None
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if len(ops) != 1 or ops[0][0] != 'insert' or ops[0][4] - ops[0][3] != 1:
        return None
    if done[ops[0][3]] not in _PARTICLES:
        return None
    return ops[0][1]


def _chunk(line, k):
    """足した位置 k の前のかなと漢字の語と、後ろの漢字の並びをつないだ塊 (a, b)"""
    b = k
    while b < len(line) and _kanji(line[b]):
        b += 1
    if b == k:
        return None
    a = k
    while a > 0 and (_hira(line[a - 1]) or _kanji(line[a - 1])) and k - a < 3:
        a -= 1
    while a < k and not _kanji(line[a]):
        a += 1
    if a == k or not _kanji(line[a]):
        return None
    return a, b


def _rival(line, store, dict_index, kanji_guess, ime_reconvert, tokenize, k=None):
    if k is None:
        return None
    ab = _chunk(line, k)
    if ab is None:
        return None
    a, b = ab
    chunk = line[a:b]
    try:
        readings = kanji_guess.reading_combos(chunk, dict_index)[:6]
    except Exception:
        return None
    faces = {}
    for r in readings:
        for v in _variants(r):
            try:
                rows = store.lookup(v)
            except Exception:
                continue
            for e in rows or ():
                face = e.get('surface') or ''
                if not face or face == chunk or not any(_kanji(c) for c in face):
                    continue
                if not e.get('solid') or (e.get('count') or 0) < 2:
                    continue
                if ime_reconvert._rank(face) > SAFE_RANK:
                    continue
                faces[face] = v
    if len(faces) != 1:
        return None
    face = next(iter(faces))
    new = line[:a] + face + line[b:]
    try:
        toks = list(tokenize(new))
    except Exception:
        return None
    # 替えた語が解析でちょうど1語に読め、行に読めない語が無いこと
    if not any(t.start == a and t.surface == face for t in toks):
        return None
    if any(not getattr(t, 'has_reading', True) for t in toks):
        return None
    return a, b, face


def fix(line, result, store, dict_index=None):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    done = result.get('corrected')
    if not isinstance(done, str) or done == line:
        return result
    k = _inserted(line, done)
    if k is None:
        return result
    try:
        import kanji_guess
        import ime_reconvert
        from morphology import tokenize
        got = _rival(line, store, dict_index, kanji_guess, ime_reconvert, tokenize, k)
    except Exception:
        return result
    if got is None:
        return result
    a, b, face = got
    new = line[:a] + face + line[b:]
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'corrected': new, 'changed': True, 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [[line[a:b], face, 'かな入力']], 'odd_spans': [], 'odd_reasons': []})
    out.pop('unsure_spans', None)
    return out


def correct_line(line, store=None, *args, **kwargs):
    result = _orig['correct_line'](line, store, *args, **kwargs)
    try:
        # 位置の引数は context_vocab, decisions, input_method, context_vec, dict_index の順（correction_entry.correct_line）
        method = kwargs.get('input_method', args[2] if len(args) > 2 else 'kana')
        if method != 'kana':
            return result
        di = kwargs.get('dict_index', args[4] if len(args) > 4 else None)
        return fix(line, result, store, di)
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
