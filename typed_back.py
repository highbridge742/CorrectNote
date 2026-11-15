# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""ローマ字入力で英字が残り、IME が前後を別の漢字にした語を、打った読みに戻してから直す（2026-11-13・全体評価スレッド）。

なぜ
----
ローマ字入力で1打ずれると、母音の付かない子音が英字のまま残り、IME は残りのかなだけを漢字にする
（作った例: でんしゃ に m が紛れて「田m者」）。表記から読みを作ると「たmしゃ」になり、打った読み
「でんmしゃ」には届かないので、紫は付くが正しい候補が1度も作られない。かなと英字だけの形
（作った例:「にもhつ」）は前からの読み直しで直るので、足りないのは「打った読みに戻す」所だけ。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。
1. 前からの補正が何も直さず、行に英字が残っている時だけ見る。
2. 英字を含む並びのうち、打った読み（かな＋英字）が分かる所を探す。読みは set_provider() で渡された
   関数（表記 → 読みの並び）に聞く。渡されていなければ何もしない。
3. その所を打った読みに置き換えた行を、前からの補正にもう1度通す。
4. 採るのは次が全部そろう時だけ。それ以外は元の答え（紫のまま）。
   - 置き換えた所の外は1字も変わっていない
   - 置き換えた所に英字も紫も残っていない
   - 直った語の読みが、打った読みの1打の戻し（前からの決まり: 隣の入れ替え・隣のキー・巻き込みの抜き）の1つで、
     ほかの戻しより行の費用が安い（並べば採らない）
特定の語や文字列には合わせない。

切り替え: CN_TYPED_BACK=0 で前のまま。
"""
import functools
import os
import threading
import unicodedata

MAX_CHUNK = 16      # 読みを聞く並びの字数の上限（1回の確定の文節はこれより短い）
MAX_TRIES = 2       # 1行で通し直す回数の上限（1回ごとに補正の通しが1行分）

_orig = {}
_local = threading.local()
_provider = [None]
STATS = {'lines': 0, 'tries': 0, 'fixed': 0}


def _on():
    return os.environ.get('CN_TYPED_BACK') != '0'


def set_provider(fn):
    """fn(表記) → 打った読み（かな＋半角英字）の並び。None で外す。"""
    _provider[0] = fn


def _is_letter(c):
    return ('a' <= c <= 'z') or ('ａ' <= c <= 'ｚ')


def _is_japanese(c):
    return ('぀' <= c <= 'ヿ') or ('一' <= c <= '鿿') or c == '々'


def _chunks(line, ask):
    """英字を含み、打った読みの分かる並び（始め, 終わり, 読み）。長い並びを先に、重なりは採らない。"""
    letters = [i for i, c in enumerate(line) if _is_letter(c)]
    if not letters:
        return []
    found = []
    taken = set()
    for size in range(min(MAX_CHUNK, len(line)), 1, -1):
        for s in range(0, len(line) - size + 1):
            e = s + size
            if not any(s <= i < e for i in letters) or any(i in taken for i in range(s, e)):
                continue
            surface = line[s:e]
            if not any(_is_japanese(c) for c in surface):
                continue
            try:
                readings = ask(surface) or ()
            except Exception:
                readings = ()
            for rd in readings:
                rd = unicodedata.normalize('NFKC', rd or '').lower()
                if rd and rd != unicodedata.normalize('NFKC', surface).lower() and any('a' <= c <= 'z' for c in rd):
                    found.append((s, e, rd))
                    taken.update(range(s, e))
                    break
    return sorted(found)


def _reading(text):
    from morphology import tokenize
    kt = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
    out = ''
    for t in tokenize(text):
        out += (t.reading if t.has_reading else t.surface).translate(kt)
    return out


def _one_slip(typed, new, pre='', post=''):
    """直った語の読みが、打った読みの1打の戻し（前からの決まり odd_respell._romaji_key_repairs: 隣の入れ替え・
    隣のキー・巻き込みの抜き）のどれかで、ほかの戻しより行の費用が高くないか。並ぶ戻しが在れば採らない。"""
    import odd_respell
    import morphology
    rd = _reading(new)
    if not rd:
        return False
    repairs = odd_respell._romaji_key_repairs(typed)
    if rd not in repairs:
        return False
    mine = morphology.path_cost(pre + rd + post)
    for other in repairs:
        if other != rd and morphology.path_cost(pre + other + post) <= mine:
            return False
    return True


def _try(line, result, chunk, call):
    s, e, typed = chunk
    pre, post = line[:s], line[e:]
    back = pre + typed + post
    again = call(back)
    if not isinstance(again, dict):
        return None
    got = again.get('corrected')
    if not isinstance(got, str) or got == back or len(got) < len(pre) + len(post):
        return None
    if not got.startswith(pre) or (post and not got.endswith(post)):
        return None
    new = got[len(pre):len(got) - len(post)]
    if not new or any(_is_letter(c) or ('A' <= c <= 'Z') for c in new):
        return None
    for span in again.get('odd_spans') or ():
        if span[0] < s + len(typed) and span[1] > s:
            return None
    if not _one_slip(typed, new, pre, post):
        return None
    out = dict(result)
    out['corrected'] = got
    out['changed'] = True
    out['details'] = list(result.get('details') or ()) + [[line[s:e], new, '打った読みに戻して直した']]
    out['spans'] = list(result.get('spans') or ()) + [[s, s + len(new)]]
    out['original_spans'] = list(result.get('original_spans') or ()) + [[s, e]]
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if not (x[0] < e and x[1] > s)]
    if 'odd_reasons' in result and len(result.get('odd_reasons') or ()) == len(result.get('odd_spans') or ()):
        out['odd_reasons'] = [r for x, r in zip(result['odd_spans'], result['odd_reasons'])
                              if not (x[0] < e and x[1] > s)]
    if 'unsure_spans' in result:
        out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if not (x[0] < e and x[1] > s)]
    return out


def correct_line(line, *args, **kwargs):
    fn = _orig['correct_line']
    result = fn(line, *args, **kwargs)
    ask = _provider[0]
    if ask is None or not _on() or getattr(_local, 'busy', False):
        return result
    if kwargs.get('input_method', 'kana') != 'romaji' or kwargs.get('defer_heavy'):
        return result
    if not isinstance(line, str) or not isinstance(result, dict) or result.get('corrected') != line:
        return result
    if not any(_is_letter(c) for c in line):
        return result
    _local.busy = True
    try:
        chunks = _chunks(line, ask)
        if not chunks:
            return result
        STATS['lines'] += 1
        kw = dict(kwargs)
        kw.pop('on_early_odd', None)
        for chunk in chunks[:MAX_TRIES]:
            STATS['tries'] += 1
            fixed = _try(line, result, chunk, lambda text: fn(text, *args, **kw))
            if fixed is not None:
                STATS['fixed'] += 1
                return fixed
        return result
    except Exception:
        return result
    finally:
        _local.busy = False


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    # 呼ぶ側（analysis_worker）は inspect.signature で引数を確かめる。包みが元の関数の引数の形を見せるようにする
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
