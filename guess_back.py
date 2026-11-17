# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""推し量りだけの直しの後に、その所かすぐ隣に紫が残るなら、直しを戻して紫だけにする（2026-11-14 補正担当・未解決タブ）。

なぜ
----
書き手が IME で選んだ漢字を、読みの手がかりなしに消す・別の語にする直し（作った例: 差釣れません → 差れません、
誤変換の佑 → 多角）は推し量り。直した後もその辺りに紫が残るなら、直しが当たっていない見込みが高い。
誤った直しより紫のほうがよい（全体評価の方針）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
1. 直しの details がどれも推し量り（理由が 常用外の字・脱字、または漢字を含む所を消しただけの直し）か見る。
2. 直した所（元の行の位置）に重なるか隣り合う紫、または同じひらがなの続きの中の紫が在れば、行を元に戻し、直した所を紫にする（ほかの紫はそのまま）。
特定の語や文字列には合わせない。切り替え: CN_GUESS_BACK=0 で前のまま。
"""
import difflib
import functools
import os

GUESS_REASON = ('常用外の字',)
REASON = '打ち違いの見込みはあるが、直し先を決められない'
_orig = {}


def _on():
    return os.environ.get('CN_GUESS_BACK') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _guess(d):
    if not isinstance(d, (list, tuple)) or len(d) < 2:
        return False
    src, face = d[0], d[1]
    why = d[2] if len(d) > 2 else ''
    if why in GUESS_REASON or (isinstance(why, str) and why.startswith('脱字')):
        return True          # 脱字の足し（なであり → なでてあり）も、読みの手がかりの無い推し量り
    return isinstance(src, str) and face == '' and any(_kanji(c) for c in src)


def _same_kana_run(line, m, o):
    """2つの所が、元の行の同じひらがなの続き（全て｜ひらがなであり の ひらがなであり）の中に在るか。
    かなの続きの切り方が崩れると、紫と直しが同じ続きの中で離れて付く。"""
    hira = lambda c: 'ぁ' <= c <= 'ゖ' or c == 'ー'
    lo, hi = min(m[0], o[0]), max(m[1], o[1])
    lo, hi = max(lo, 0), min(hi, len(line))
    return hi > lo and all(hira(c) for c in line[lo:hi])


def back(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected') or line
    det = result.get('details') or ()
    if text == line:
        return _drop_stale(result)
    if not det or not all(_guess(d) for d in det):
        return result
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    if not odd:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
    marks = [(o[1], max(o[2], o[1] + 1)) for o in ops]
    if not any(a <= y and x <= b or _same_kana_run(line, (a, b), (x, y)) for a, b in marks for x, y in odd):
        return result
    # 直しを戻したので、直した後の不自然さの紫（fixed_still_odd）は当たらない
    try:
        import fixed_still_odd as _fso
        stale = _fso.REASON
    except Exception:
        stale = None
    keep_r = [r for r in result.get('odd_reasons') or () if not (len(r) > 2 and r[2] == stale)]
    gone = {tuple(r[:2]) for r in result.get('odd_reasons') or () if len(r) > 2 and r[2] == stale} \
        - {tuple(r[:2]) for r in keep_r}
    odd = [x for x in odd if x not in gone]
    out = dict(result)
    spans = sorted(set(odd) | set(marks))
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': [],
                'odd_spans': spans,
                'odd_reasons': keep_r + [(a, b, REASON) for a, b in marks]})
    return out


def _drop_stale(result):
    """書き換えの無い答えに残る「直した後も不自然」の紫（fixed_still_odd）は、指す直しが戻されて無いので外す
    （2026-11-14 未解決タブの正しい文: 外側の段が直しを戻した後に紫だけ残った）。既定はオフ"""
    # 既定はオフ（CN_GUESS_BACK_STALE=1 で入る）: 692行の打ち違いで、直しが戻された後のこの紫だけが残りの誤り
    # （離れた所の打ち違い）の印だった行が紫を失った（2026-11-14）
    # 書き換えの無い答えに直しの控え（details）だけが残る行は、直しが外側の段で戻された跡がはっきりしているので、既定で外す
    # （作った例: 型番の英字の直しを戻した後に「直した後も…」の紫だけが残った）。CN_GUESS_BACK_STALE_DET=0 で前のまま
    det_left = bool(result.get('details')) and os.environ.get('CN_GUESS_BACK_STALE_DET') != '0'
    if (os.environ.get('CN_GUESS_BACK_STALE') != '1' and not det_left) or not result.get('odd_spans'):
        return result
    try:
        import fixed_still_odd as _fso
        stale = _fso.REASON
    except Exception:
        return result
    reasons = result.get('odd_reasons') or ()
    gone = {tuple(r[:2]) for r in reasons if len(r) > 2 and r[2] == stale}
    if not gone:
        return result
    other = {tuple(r[:2]) for r in reasons if not (len(r) > 2 and r[2] == stale)}
    gone -= other
    if not gone:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if tuple(x[:2]) not in gone]
    out['odd_reasons'] = [r for r in reasons if tuple(r[:2]) not in gone]
    return out


_AUX = frozenset(('くる', 'いく', 'いる', 'おく', 'みる', 'しまう', 'もらう', 'くれる', 'あげる', 'ある', 'ほしい'))


def _bad_de(p, t):
    """で が、で の付かない動詞の形に付いているか。で が付くのは撥音便（読ん・飛ん）と ぐ の動詞のイ音便（泳い）だけで、
    く の動詞のイ音便（咲い・さい）に で は付かない（咲いて）。文法どおりの形ではないので、打ち違いの跡でありうる
    （2026-11-17 うに: さいでいか → 最大化 の直しを、て＋補助の動詞として戻していた）。CN_GUESS_BACK_TE_AUX_DE=0 で前のまま"""
    if os.environ.get('CN_GUESS_BACK_TE_AUX_DE') == '0' or t.surface != 'で':
        return False
    base = p.base_form or ''
    return p.surface.endswith('い') and base.endswith('く') and base not in ('行く', 'いく')


def _te_aux_spots(line):
    """元の行の 動詞＋て／で（接続助詞）＋補助の動詞（くる・いる・しまう…）の て／で の位置"""
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return []
    out = []
    for k in range(1, len(toks) - 1):
        t, p, n = toks[k], toks[k - 1], toks[k + 1]
        if (t.surface in ('て', 'で') and t.pos == '助詞' and p.pos == '動詞' and p.end == t.start
                and n.pos in ('動詞', '形容詞') and n.start == t.end and (n.base_form or '') in _AUX
                and not _bad_de(p, t)):
            out.append((t.start, t.end))
    return out


def te_aux_back(line, result):
    """書き換えが、元の行の 動詞＋て＋補助の動詞（出てきた・見ている）の て／で を消す・替えるなら、その書き換えを戻す
    （2026-11-16 うに 未解決タブの正しい文: 出てきた → 出来た）。て＋補助の動詞は文法どおりの形で、打ち違いの跡ではない。
    CN_GUESS_BACK_TE_AUX=0 で前のまま"""
    if os.environ.get('CN_GUESS_BACK_TE_AUX') == '0' or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    if not isinstance(text, str) or text == line:
        return result
    spots = _te_aux_spots(line)
    if not spots:
        return result
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    bad = [o for o in ops if o[0] != 'equal' and any(o[1] <= a and b <= o[2] for a, b in spots)]
    if not bad:
        return result
    pieces, gone_src = [], []
    for o in ops:
        if o in bad:
            pieces.append(line[o[1]:o[2]])
            gone_src.append((line[o[1]:o[2]], text[o[3]:o[4]]))
        else:
            pieces.append(text[o[3]:o[4]])
    new = ''.join(pieces)
    out = dict(result)
    lops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out['corrected'] = new
    out['changed'] = new != line
    out['spans'] = [[o[3], o[4]] for o in lops]
    out['original_spans'] = [[o[1], o[2]] for o in lops]
    out['details'] = [d for d in (result.get('details') or ())
                      if not (isinstance(d, (list, tuple)) and len(d) > 1
                              and any(str(d[0]) in src or str(d[1]) in dst for src, dst in gone_src))]
    return out


_TAIL_PARTICLES = frozenset('をはへがにでともの')
TAIL_REASON = '最後のかなは助詞の打ち違いかもしれません（直し先を決められません）'


def tail_drop_mark(line, result):
    """かなの所を語に直すとき、行の終わりの1字のかなを余計な1打として落とした直し（へんじほ → 返事）で、その1字のキーの
    隣（シフトの面も含む）に助詞（を・は・へ…）があるなら、落とした字は助詞の打ち違いでもありうる。直しは残して、その所に
    紫を付ける（2026-11-17 うに: 1行だけの へんじほ の扱い。を・は・へ が並ぶので決めずに紫）。
    CN_GUESS_BACK_TAIL_DROP=0 で前のまま"""
    if os.environ.get('CN_GUESS_BACK_TAIL_DROP') == '0' or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    if not isinstance(text, str) or text == line:
        return result
    end = len(line.rstrip('。、．，！？!? 　'))
    try:
        import kana_layout as K
        import collocation_repair as C
    except Exception:
        return result
    add, wo = [], []
    for d in result.get('details') or ():
        if not (isinstance(d, (list, tuple)) and len(d) > 2 and isinstance(d[0], str) and isinstance(d[1], str)):
            continue
        src, dst = d[0], d[1]
        if len(src) < 2 or not all('ぁ' <= c <= 'ゖ' for c in src) or not any(_kanji(c) for c in dst):
            continue
        if line[end - len(src):end] != src or src[-1] in _TAIL_PARTICLES:
            continue
        try:
            if C._word_reading(dst) != src[:-1]:
                continue
            near = [c for c, dist in K.nearby_candidates(src[-1], include_phonetic=False) if 0 < dist <= 1.0]
            keys = set(near)
            for c in near:
                keys.update(K.same_key_characters(c))
        except Exception:
            continue
        if 'を' in keys and os.environ.get('CN_GUESS_BACK_TAIL_WO') != '0':
            # 隣のキー（シフトの面）が を なら、を の打ち違いとして 返事を と直す（2026-11-17 うに 決定カード「返事を」:
            # 名詞で終わる行の最後のかな1字は、文の途中で改行した所の助詞 を が多い）。CN_GUESS_BACK_TAIL_WO=0 で紫だけ
            tail = len(text.rstrip('。、．，！？!? 　'))
            if text[tail - len(dst):tail] == dst:
                wo.append((d, tail))
                continue
        if keys & _TAIL_PARTICLES:
            add.append((end - len(src), end))
    if wo:
        (d, tail), = wo[:1]
        text = text[:tail] + 'を' + text[tail:]
        out = dict(result)
        out['corrected'] = text
        out['changed'] = True
        out['details'] = [(x[0], x[1] + 'を', *x[2:]) if x is d else x for x in result.get('details') or ()]
        lops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
        out['spans'] = [[o[3], o[4]] for o in lops]
        out['original_spans'] = [[o[1], o[2]] for o in lops]
        drop = (end - len(d[0]), end)
        out['odd_spans'] = [x for x in result.get('odd_spans') or () if not (x[0] < drop[1] and drop[0] < x[1])]
        out['odd_reasons'] = [r for r in result.get('odd_reasons') or () if not (r[0] < drop[1] and drop[0] < r[1])]
        if 'unsure_spans' in result:
            out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if not (x[0] < drop[1] and drop[0] < x[1])]
        return out
    if not add:
        return result
    out = dict(result)
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    out['odd_spans'] = list(result.get('odd_spans') or ()) + [list(a) for a in add if a not in odd]
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [(a, b, TAIL_REASON) for a, b in add]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        return tail_drop_mark(line, back(line, te_aux_back(line, result)))
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
