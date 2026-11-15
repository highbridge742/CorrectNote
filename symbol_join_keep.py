"""キー1つで打つ記号（＝ ＋ など）を消して両側を1つに解いた書き換えを採らない（2026-11-14 補正担当）。

なぜ
----
メモでは「語＝語」「語＋語」のように、記号で2つの語をつなぐ書き方が普通（作った例: 買う＝かう・泳ぐ＝運動）。
かな入力の段が記号をかなの打ち違いと読んで、記号をまたいで1つの語に解くと（買う＝ → 解放）、正しい行が崩れる
（全体評価の方針 v2 の A: 記号をまたいで1つの語として解かない）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（答えが出た後に見る）。
1. 元の行の記号のうち、broken_shape._STRAY_SYMBOL に当たり、記号を抜いても両側が1つの語にならない所
   （broken_shape._symbol_splits_word が偽: 両側がそれぞれ語）を「語をつなぐ記号」と見る。
2. 答えの書き換えがその記号を消していたら（答えの中のその記号の数が減った）、行の書き換えを採らず元の行に戻す。
   書き換えに掛かっていた紫も外す（打ったままで成り立つ行なので）。
特定の語や文字列には合わせない。

切り替え: CN_SYMBOL_JOIN_KEEP=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}


def _on():
    return os.environ.get('CN_SYMBOL_JOIN_KEEP') != '0'


def joining_symbols(line):
    """語をつなぐ記号の位置 [(始め, 終わり)]。"""
    try:
        import broken_shape as B
    except Exception:
        return []
    out = []
    for m in B._STRAY_SYMBOL.finditer(line):
        if not B._symbol_splits_word(line, m.start(), m.end()):
            out.append((m.start(), m.end()))
    return out


def keep(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    if not isinstance(text, str) or text == line:
        return result
    syms = joining_symbols(line)
    if not syms:
        return result
    lost = any(text.count(line[a:b]) < line.count(line[a:b]) for a, b in syms)
    if not lost:
        return result
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    touched = [(i1, max(i2, i1 + 1)) for tag, i1, i2, j1, j2 in ops if tag != 'equal']
    out = dict(result)
    out['corrected'] = line
    out['changed'] = False
    out['details'] = []
    out['spans'] = []
    out['original_spans'] = []

    # 書き換えを採らなかった時に段が残した紫（理由に「直」が入る: 直し先を決められない など）も、書き換えが無くなれば要らない
    fixed_why = {tuple(x[:2]) for x in result.get('odd_reasons') or ()
                 if len(x) >= 3 and isinstance(x[0], int) and isinstance(x[2], str) and '直' in x[2]}

    def far(x):
        return tuple(x[:2]) not in fixed_why and not any(x[0] < e and x[1] > s for s, e in touched)
    for key in ('odd_spans', 'unsure_spans'):
        if key in result:
            out[key] = [x for x in result.get(key) or () if len(x) >= 2 and isinstance(x[0], int) and far(x)]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [x for x in result.get('odd_reasons') or ()
                              if len(x) >= 2 and isinstance(x[0], int) and far(x)]
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
    # 呼ぶ側（analysis_worker）は inspect.signature で引数を確かめる。包みが元の関数の引数の形を見せるようにする
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
