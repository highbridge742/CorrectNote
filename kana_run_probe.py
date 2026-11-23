# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""文の中のかなの並びが、短い語の切れ端（2字以下の名詞と助詞）にしか読めない時は、その並びだけを補正に通して
比べる（2026-11-23 補正担当、うに 誤判定タブ: かなの並び1つだけの行は漢字の語に直るのに、同じ並びが文の中に
在ると「元の文が成り立つ」と見られ、直らず紫も付かなかった）。

なぜ
----
かなの並びの漢字化は、並びが辞書の語の並びに読めるなら見送る。2字以下の名詞と助詞の切れ端でも読めてしまうので、
打ち違いのかなの並びが文の中に在ると、1つだけの行なら届く直しに届かない。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
かな入力で、答えが元の行のままのとき、行の頭か ひらがな以外の字の後ろから始まり、助詞1字で終わる4字以上の
ひらがなの並びのうち、解析の語がどれも2字以下で、名詞が2つ以上・動詞・形容詞・助動詞の無いものを探す。
その並び（終わりの助詞を除く）だけを同じ補正に通し、並び全体が漢字を含む1つの語に直り、紫が無ければ（行のほかの所の紫は位置をずらして残す）、
行のその所を替えて採る。替えた行でその所が語の切れ目に当たらないか、読めない語が在れば採らない。
切り替え: CN_KANA_RUN_PROBE=0 で前のまま。
"""
import functools
import os

_orig = {}
_BUSY = []
_END = set('をがにではもへとの')


def _on():
    return os.environ.get('CN_KANA_RUN_PROBE') != '0'


def _hira(c):
    return 'ぁ' <= c <= 'ゖ' or c == 'ー'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def spots(line):
    """[(a, b)]: 試す並び（終わりの助詞は含めない）"""
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return []
    out = []
    k = 0
    while k < len(line):
        if not _hira(line[k]) or (k > 0 and _hira(line[k - 1])):
            k += 1
            continue
        j = k
        while j < len(line) and _hira(line[j]):
            j += 1
        k0 = k
        k = j
        # 並びの終わりの助詞1字（めいでかい｜を）までを1つの並びとする
        inner = [t for t in toks if k0 <= t.start and t.end <= j]
        if not inner or inner[0].start != k0:
            continue
        # 終わりの助詞を探す: 並びの中の最後の助詞1字で、その後ろが並びの終わり
        end = None
        for t in inner:
            if t.pos == '助詞' and len(t.surface) == 1 and t.surface in _END and t.end == j:
                end = t
        if end is None:
            continue
        body = [t for t in inner if t.end <= end.start]
        if end.start - k0 < 4 or len(body) < 3:
            continue
        if any(len(t.surface) > 2 for t in body):
            continue
        if any(t.pos in ('動詞', '形容詞', '助動詞', '副詞', '連体詞', '感動詞') for t in body):
            continue
        if sum(1 for t in body if t.pos == '名詞') < 2:
            continue
        # 頭は自立の名詞（代名詞・接尾・助詞で始まる並び: これ｜は・たち｜は・の｜うしろ は普通の書き方）
        if body[0].pos != '名詞' or str(body[0].pos_sub or '').startswith(('代名詞', '接尾', '非自立')):
            continue
        out.append((k0, end.start))
    return out


def _drop_stale(result):
    """行が元のままなのに「直した後も…」（直しが在ったから付いた紫の理由）だけの紫は、途中の段が直して戻した跡なので
    外す（2026-11-23 補正担当: 写しのアプリで、直していない行の離れた所にこの紫だけが残っていた）。
    既定オフ（CN_KANA_RUN_PROBE_STALE=1 で入る）: 誤字の束692で、直していない行の本当の打ち違いの所（…が鳴かな…）に
    付いていた同じ理由だけの紫も消えた。理由の文だけでは分けられない"""
    if os.environ.get('CN_KANA_RUN_PROBE_STALE') != '1' or not result.get('odd_spans'):
        return result
    why = set()
    for mod in ('fixed_still_odd', 'rewrite_doubt'):
        try:
            why.add(__import__(mod).REASON)
        except Exception:
            pass
    reasons = result.get('odd_reasons') or ()
    stale = {tuple(r[:2]) for r in reasons if len(r) > 2 and r[2] in why}
    stale -= {tuple(r[:2]) for r in reasons if len(r) > 2 and r[2] not in why}
    if not stale:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if tuple(x[:2]) not in stale]
    out['odd_reasons'] = [r for r in reasons if tuple(r[:2]) not in stale]
    return out


def probe(line, result, call):
    """call(text) → 補正の答え。直せた所を替えた答えか、元の result"""
    if not _on() or _BUSY or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line:
        return result
    result = _drop_stale(result)
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    # 試す並びに掛かる紫が在る所は見ない（離れた所の紫はそのまま残す）
    sp = [(a, b) for a, b in spots(line) if not any(x < b + 1 and a < y for x, y in odd)]
    if not sp:
        return result
    new = line
    details = []
    for a, b in sorted(sp, reverse=True):
        run = line[a:b]
        _BUSY.append(1)
        try:
            r = call(run)
        except Exception:
            r = None
        finally:
            _BUSY.pop()
        if not isinstance(r, dict) or r.get('odd_spans'):
            continue
        face = r.get('corrected') or run
        if face == run or not any(_kanji(c) for c in face) or any(_hira(c) for c in face):
            continue
        cand = new[:a] + face + new[b:]
        try:
            from morphology import tokenize
            toks = list(tokenize(cand))
        except Exception:
            continue
        # 替えた語の所が解析の語の切れ目で始まり・終わり、どの語も読めること（最大｜化 のような2語でもよい）
        e = a + len(face)
        if not any(t.start == a for t in toks) or not any(t.end == e for t in toks):
            continue
        if any(not getattr(t, 'has_reading', True) for t in toks if t.start < e and a < t.end):
            continue
        new = cand
        details.append([run, face, 'かな入力'])
    if new == line:
        return result
    import difflib
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    def mv(i):
        for tag, i1, i2, j1, j2 in ops_all:
            if i1 <= i <= i2:
                return j1 + min(i - i1, j2 - j1)
        return i
    ops_all = difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes()
    odd_s = [[mv(x[0]), mv(x[1])] for x in result.get('odd_spans') or ()]
    odd_r = [[mv(r[0]), mv(r[1])] + list(r[2:]) for r in result.get('odd_reasons') or ()]
    out.update({'corrected': new, 'changed': True, 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops], 'details': details[::-1],
                'odd_spans': odd_s, 'odd_reasons': odd_r})
    if os.environ.get('CN_KANA_RUN_PROBE_REMARK') != '0':
        # 「直した後も…」の紫は、途中の段の別の直し（後で戻された）に付いた理由。この直しの後の行で測り直す
        # （2026-11-23 補正担当、写しのアプリの誤判定タブ: 戻された直しの紫が、この直しの後も離れた所に残った）。
        # CN_KANA_RUN_PROBE_REMARK=0 で前のまま
        try:
            import fixed_still_odd as F
            stale = {tuple(r[:2]) for r in odd_r if len(r) > 2 and r[2] == F.REASON}
            stale -= {tuple(r[:2]) for r in odd_r if len(r) > 2 and r[2] != F.REASON}
            if stale:
                base = dict(out)
                base['odd_spans'] = [x for x in odd_s if tuple(x[:2]) not in stale]
                base['odd_reasons'] = [r for r in odd_r if tuple(r[:2]) not in stale]
                if not base['odd_spans']:
                    out = F._mark(line, base)
        except Exception:
            pass
    return out


def correct_line(line, store=None, *args, **kwargs):
    result = _orig['correct_line'](line, store, *args, **kwargs)
    try:
        method = kwargs.get('input_method', args[2] if len(args) > 2 else 'kana')
        if method != 'kana' or not isinstance(line, str):
            return result
        import correction_entry as ce        # 外側の包み（一覧の語・紫の理由）も通した答えで比べる
        return probe(line, result, lambda text: ce.correct_line(text, store, *args, **kwargs))
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
