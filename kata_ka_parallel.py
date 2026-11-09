# -*- coding: utf-8 -*-
"""片仮名の名詞＋化＋片仮名の名詞（クリック｜化｜ドラッグ）を、並べる か の選び違いかもしれない所として紫にする
（2026-11-09 手分けA）。

接尾の 化 の後ろに助詞を挟まず片仮名の名詞が続き、X化 が辞書の語でない（表に読みが無い）とき、並立の か（AかB）と
読み（か）が同じなので、IME の選び違いと区別できない。直しの決め手（どちらの形が多いか）は行の中に無いので、
直さず紫だけにする。打った記録も IME も使わない。特定の語には合わせない。CN_KATA_KA_PARALLEL=0 で見ない。
"""
import os


def _on():
    return os.environ.get('CN_KATA_KA_PARALLEL') != '0'


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in s)


def propose(text):
    from morphology import tokenize
    import corrector
    toks = list(tokenize(text))
    out = []
    for i in range(1, len(toks) - 1):
        x, k, y = toks[i - 1], toks[i], toks[i + 1]
        if k.surface != '化' or not (k.pos_sub or '').startswith('接尾'):
            continue
        if x.pos != '名詞' or y.pos != '名詞' or not _kata(x.surface) or not _kata(y.surface) or len(y.surface) < 2:
            continue
        if x.end != k.start or k.end != y.start:
            continue
        if corrector._table_readings_for_surface(x.surface + k.surface):
            continue           # 表に在る X化（スリム化・コード化）は語
        out.append((k.start, k.end))
    return out


def repair_line(line, result, decided=()):
    if not _on() or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done != line:
        return result          # 直した行では位置を合わせない（元の行のままの時だけ）
    try:
        marks = propose(done)
    except Exception:
        return result
    now = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    add = [m for m in marks if not any(a < m[1] and m[0] < b for a, b in now + list(decided or ()))]
    if not add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(now) | set(add))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, '片仮名の語のあいだの「化」は、並べる「か」かもしれません') for a, b in add]
    return out
