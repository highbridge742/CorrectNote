# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""空白・括弧・矢印などで区切られた語句を、紫が残った時はそこだけで見直す（2026-11-14・全体評価スレッド）。

なぜ
----
1語だけの行なら直る語が、かぎ括弧の中や、空白・矢印で並べた行の中だと直らない（うにさん 2026-11-14 02:36Z。
作った例: 「かいき゛しつ」だけの行は 会議室 になるのに、かぎ括弧に入れて後ろに文を続けると別の語になる）。
行を通して読むと、区切りの向こうの字と1つの文として解こうとして、区切りの中の語の候補が負ける。
空白・括弧・矢印は書き手が置いた区切りなので、その中は1つのまとまりとして単体でも読める。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。
1. 行を、空白・括弧・記号（矢印・等号など。、。・！？ は区切りにしない）で語句に分ける。語句が1つだけの行は見ない。
2. 前からの補正の答えで、紫が掛かったままの語句と、括弧のすぐ内側で書き換えられた語句を、単体で補正に通す。
   紫の残る行では、紫の無いほかの語句も通す（紫の無い行の語句は見ない）。
3. 単体の答えに紫が無ければ、その語句の所だけ単体の答えに置き換え、その語句の紫を外す。
   単体でも紫が残るなら前の答えのまま。
行を先に切って解くのではない（切らずに解いた答えが先。紫の残った所だけ後から見直す）。
1行で単体に通すのは MAX_CHUNKS 回まで（1回ごとに補正の通しが語句1つ分）。打鍵中の軽い答え（defer_heavy）では見ない。
2026-11-14 昼: 語のすぐ後ろの括弧の中のかな（読みがなの書き添え）は見ない。
2026-11-14 昼3: 空白を挟まずにキー1つで打てる記号（等号など）で隣の字とつながる語句は単体で見ない（記号が打ち違いの一部のことがある。紫は前のまま）。
2026-11-14 昼2: かなの語句の単体の答えが隣の語句と同じ字になる時は置かない（記号でつないだ読み・言い換えの書き添え）。
特定の語や文字列には合わせない。

切り替え: CN_CHUNK_ALONE=0 で前のまま。
"""
import difflib
import functools
import os
import threading
import unicodedata

MAX_CHUNKS = 4
REASON = '区切られた語句を単体で見直した'

_orig = {}
_local = threading.local()
STATS = {'lines': 0, 'tries': 0, 'fixed': 0, 'cleared': 0}


def _on():
    return os.environ.get('CN_CHUNK_ALONE') != '0'


def _separator(c):
    if c in '゛゜':
        return False                      # かな入力の濁点・半濁点のキーは字の一部
    if c.isspace():
        return True
    return unicodedata.category(c) in ('Ps', 'Pe', 'Pi', 'Pf', 'Sm', 'So', 'Sk', 'Sc')


def _open(c):
    return unicodedata.category(c) in ('Ps', 'Pi')


def _close(c):
    return unicodedata.category(c) in ('Pe', 'Pf')


def _japanese(s):
    return any(('ぁ' <= c <= 'ゖ') or ('ァ' <= c <= 'ヺ') or ('一' <= c <= '鿿') for c in s)


def _kana_only(s):
    return bool(s) and all(('ぁ' <= c <= 'ゖ') or ('ァ' <= c <= 'ヺ') or c in 'ー゛゜' for c in s)


def _gloss(line, s, e):
    """語のすぐ後ろの括弧の中の、かなだけの語句（紅葉（もみじ）の形）。読みがなの書き添えなので、単体で通して
    漢字にしたり直したりしない（2026-11-14 PC の作った例で、読みがなが漢字に置き換わった）。"""
    return (s >= 2 and e < len(line) and _open(line[s - 1]) and _close(line[e]) and not _separator(line[s - 2])
            and _kana_only(line[s:e]))


def _symbol(c):
    # キー1つで打てる記号だけ（半角・全角の = + ^ | ~ $ など）。矢印のように変換して出す記号は、書き手が置いた区切り
    return unicodedata.category(c) in ('Sm', 'So', 'Sk', 'Sc') and ord(unicodedata.normalize('NFKC', c)[:1] or 'あ') < 128


def _glued(line, s, e):
    """語句が、空白を挟まずにキー1つで打てる記号（等号など。矢印・括弧・空白は別）で隣のかな・漢字とつながっている。
    記号そのものが打ち違いの一部のことがある（語の途中に記号のキーが入った形）ので、そこで切って単体で直さない。
    紫は前のまま残る（2026-11-14 補正担当の束の1行: 記号をまたぐ1語の打ち違いの前半だけが別の語に書き換わり、紫が消えた）。
    CN_CHUNK_ALONE_GLUED=1 で前のまま。"""
    if os.environ.get('CN_CHUNK_ALONE_GLUED') == '1':
        return False
    if s >= 2 and _symbol(line[s - 1]) and _japanese(line[s - 2]):
        return True
    return e + 1 < len(line) and _symbol(line[e]) and _japanese(line[e + 1])


def chunks(line):
    """区切りで分けた語句 [(始め, 終わり, 括弧のすぐ内側か)]。かな・漢字を含む語句だけ。"""
    out, s = [], None
    for i, c in enumerate(line + ' '):
        if i < len(line) and not _separator(c):
            if s is None:
                s = i
            continue
        if s is not None:
            if _japanese(line[s:i]):
                quoted = s > 0 and _open(line[s - 1]) and i < len(line) and _close(line[i])
                out.append((s, i, quoted))
            s = None
    return out


def _region(ops, s, e):
    """元の行の [s, e) が、答えの文のどこか。書き換えが語句の外へはみ出していれば None。"""
    cs = ce = None
    for tag, i1, i2, j1, j2 in ops:
        if i2 <= s and not (i1 == i2 == s):
            continue
        if i1 >= e:
            break
        if tag == 'equal':
            lo, hi = j1 + max(s, i1) - i1, j1 + min(e, i2) - i1
        else:
            if i1 < s or i2 > e:
                return None
            lo, hi = j1, j2
        cs = lo if cs is None else min(cs, lo)
        ce = hi if ce is None else max(ce, hi)
    if cs is None or ce is None:
        return None
    return cs, ce


def _hit(spans, s, e):
    return any(x[0] < e and x[1] > s for x in spans or ())


def _splice(line, result, s, e, new):
    """元の行の語句 [s, e) の答えを new に置き換えた結果。置けなければ None。"""
    text = result['corrected']
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    reg = _region(ops, s, e)
    if reg is None:
        return None
    cs, ce = reg
    old = text[cs:ce]
    out = dict(result)
    out['corrected'] = text[:cs] + new + text[ce:]
    out['changed'] = out['corrected'] != line
    delta = len(new) - (ce - cs)
    chunk = line[s:e]
    keep = [d for d in result.get('details') or ()
            if not (len(d) >= 2 and isinstance(d[0], str) and isinstance(d[1], str) and d[0] and d[0] in chunk
                    and (d[1] in old or not d[1]))]
    spans = []
    for x in result.get('spans') or ():
        if x[1] <= cs:
            spans.append(list(x[:2]))
        elif x[0] >= ce:
            spans.append([x[0] + delta, x[1] + delta])
    orig = [list(x[:2]) for x in result.get('original_spans') or () if not (x[0] < e and x[1] > s)]
    if new != chunk:
        keep = list(keep) + [[chunk, new, REASON]]
        spans.append([cs, cs + len(new)])
        orig.append([s, e])
    out['details'] = keep
    out['spans'] = sorted(spans)
    out['original_spans'] = sorted(orig)
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if not (x[0] < e and x[1] > s)]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [x for x in result.get('odd_reasons') or ()
                              if not (len(x) >= 2 and isinstance(x[0], int) and x[0] < e and x[1] > s)]
    if 'unsure_spans' in result:
        out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if not (x[0] < e and x[1] > s)]
    return out


def _review(line, result, call, calcs=()):
    found = chunks(line)
    if calcs and os.environ.get('CN_CHUNK_ALONE_CALC') != '0':
        # 計算した式（引用の計算）に掛かる語句は単体で通さない。単体の行には式の記録が無いので、計算の答えが元の式に
        # 戻っていた（2026-11-15 v1.19.0 の CI: 前😀1-2後 の 1-2 が計算されない）。CN_CHUNK_ALONE_CALC=0 で前のまま
        found = [f for f in found if not any(a < f[1] and f[0] < b for a, b in calcs)]
    if not found or (len(found) == 1 and found[0][1] - found[0][0] == len(line.strip())):
        return result
    text = result.get('corrected')
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    todo, rest = [], []
    near = {}
    for i, (s, e, _q) in enumerate(found):
        near[(s, e)] = tuple(line[x[0]:x[1]] for x in found[max(0, i - 1):i] + found[i + 1:i + 2])
    for s, e, quoted in found:
        if _gloss(line, s, e) or _glued(line, s, e):
            continue
        if _hit(result.get('odd_spans'), s, e):
            todo.append((s, e))
        elif quoted:
            reg = _region(ops, s, e)
            if reg is not None and text[reg[0]:reg[1]] != line[s:e]:
                todo.append((s, e))
            else:
                rest.append((s, e))
        else:
            rest.append((s, e))
    if result.get('odd_spans'):
        # 紫の残る行は、紫の無い語句も単体で見直す（1語の行なら直る語が、並べた行では紫も付かずに残る）
        todo += rest
    if not todo:
        return result
    STATS['lines'] += 1
    out = result
    for s, e in sorted(todo[:MAX_CHUNKS], reverse=True):      # 後ろから置く（前の語句の位置がずれない）
        STATS['tries'] += 1
        alone = call(line[s:e])
        if not isinstance(alone, dict) or alone.get('odd_spans'):
            continue
        new = alone.get('corrected')
        if not isinstance(new, str) or not new or any(_separator(c) for c in new):
            continue
        if new != line[s:e] and _kana_only(line[s:e]) and new in near.get((s, e), ()):
            # 単体の答えが隣の語句と同じ字になる（作った例: 作る＝つくる が 作る＝作る）。かなは隣の語の読み・言い換えの
            # 書き添えなので置かない（2026-11-14 作った正しい文624行で、記号の行の書き換えの大半がこの形）。
            # CN_CHUNK_ALONE_TWIN=1 で前のまま
            if os.environ.get('CN_CHUNK_ALONE_TWIN') != '1':
                continue
        nxt = _splice(line, out, s, e, new)
        if nxt is None or (nxt['corrected'] == out['corrected'] and len(nxt.get('odd_spans') or ()) == len(out.get('odd_spans') or ())):
            continue
        # 単体の答えが字を変えずに紫だけを外す形は採らない（打ち違いの後ろに括弧で読みを書き添えた行で、打ち違いが残ったまま
        # 紫だけ消えた・2026-11-14 挙動関連担当の通し）。紫は行全体の読みから付いたもので、単体で通っても誤りでない証にならない。
        # CN_CHUNK_ALONE_CLEAR=1 で前のまま（字を変えずに紫を外す）
        if nxt['corrected'] == out['corrected'] and os.environ.get('CN_CHUNK_ALONE_CLEAR') != '1':
            continue
        STATS['fixed' if nxt['corrected'] != out['corrected'] else 'cleared'] += 1
        out = nxt
    if out is not result and out.get('odd_spans') and os.environ.get('CN_CHUNK_ALONE_REREAD') != '0':
        # 語句を直した後にまだ紫が残る: 直した後の行を通して読み直し、紫が1つも出なければ残りの紫を外す
        # （並べた語句を直すと、隣の正しい語に付いていた紫の根拠が無くなる。字を変えずに紫だけ外す形とは別で、
        # 行を通して読んだ答えで決める）。CN_CHUNK_ALONE_REREAD=0 で読み直さない
        again = call(out['corrected'])
        if isinstance(again, dict) and again.get('corrected') == out['corrected'] and not again.get('odd_spans'):
            out = dict(out)
            out['odd_spans'] = []
            if 'odd_reasons' in out:
                out['odd_reasons'] = []
            STATS['cleared'] += 1
    return out


def correct_line(line, *args, **kwargs):
    fn = _orig['correct_line']
    result = fn(line, *args, **kwargs)
    if not _on() or getattr(_local, 'busy', False) or kwargs.get('defer_heavy'):
        return result
    if not isinstance(line, str) or not isinstance(result, dict) or not isinstance(result.get('corrected'), str):
        return result
    if not any(_separator(c) for c in line.strip()):
        return result
    _local.busy = True
    try:
        kw = dict(kwargs)
        kw.pop('on_early_odd', None)
        if 'previous_line' in kw:
            kw['previous_line'] = None
        calcs = []
        for item in kwargs.get('occurrence_calculations') or ():
            a, b = getattr(item, 'start', None), getattr(item, 'end', None)
            if isinstance(a, int) and isinstance(b, int):
                calcs.append((a, b))
        if os.environ.get('CN_CHUNK_ALONE_CALC') != '0':
            # 行の位置で書いた記録（読み・計算・打鍵）は、別の文（語句だけ・直した後の行）には当てない
            for key in ('occurrence_readings', 'occurrence_calculations', 'occurrence_strokes'):
                if key in kw:
                    kw[key] = ()
        call_fn = fn
        if os.environ.get('CN_CHUNK_ALONE_TOP') != '0':
            # 語句だけの通しも、いちばん外の補正（打った漢字を戻す ime_first_keep などの守りを含む）で見る。この包みの内側だけで
            # 通すと、行全体なら守られる打った漢字が単体の答えで別の語になった（2026-11-16 うに: 括弧の付いた行だけ 打鍵から→だから）。
            # 入れ子の通しはこの包みが busy で素通しする。CN_CHUNK_ALONE_TOP=0 で前のまま（内側だけで通す）
            try:
                import correction_entry as _ce
                call_fn = _ce.correct_line
            except Exception:
                call_fn = fn
        return _review(line, result, lambda text: call_fn(text, *args, **kw), calcs)
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
