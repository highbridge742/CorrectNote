# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""行の頭の1字の助詞（に・の・を…）を、後ろの語と合わせて別の漢字の語に替えない（2026-11-13 補正担当）。

前の行から続く文を助詞の所で改行した書き方（…ほか｜に別の道具がある）では、行が助詞で始まる。入口がその助詞を
後ろの語と1語に読み直す（に別 → 人別: ん が抜けた打ち違いとみる）と、正しい文が崩れる（未解決タブの誤判定）。
行の頭の助詞から後ろが、助詞を外しても身近な語の並びとして読めるなら、その直しだけ元に戻す（紫も付けない）。
correction_entry.correct_line を外から包む。CN_HEAD_PARTICLE_KEEP=0 で前のまま。
"""
import difflib
import os

_PARTICLES = frozenset('にのをがはでとへもや')
RARE = 560     # 助詞の後ろの語がこれより身近（ime_reconvert._rank が小さい）なら、正しく読めているとみる
_orig = {}
KEYSLIP_REASON = 'かな入力の1キーの打ち違い'
REASON = '行の頭の助詞を後ろの語と合わせた直しは、決められない'


def _rank(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face)
    except Exception:
        return 800


def _head_ok(line):
    """行の頭が1字の助詞で、すぐ後ろが漢字か片仮名を含む身近な語か。"""
    if not line or line[0] not in _PARTICLES:
        return False
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return False
    if len(toks) < 2 or toks[0].surface != line[0] or toks[0].pos != '助詞':
        return False
    nx = toks[1]
    if nx.start != 1 or nx.pos not in ('名詞', '動詞', '形容詞', '副詞', '連体詞', '接頭詞'):
        return False
    if not any('一' <= c <= '鿿' or 'ァ' <= c <= 'ヺ' for c in nx.surface):
        return False
    return _rank(getattr(nx, 'base_form', '') or nx.surface) < RARE or _rank(nx.surface) < RARE


_SMALL = str.maketrans('ぁぃぅぇぉっゃゅょゎ', 'あいうえおつやゆよわ')


def _small_toggle(line, got, i2, j1, j2):
    """元の行の頭から直した所の語の終わりまでの読みと、直した行の同じ所の読みが、小書きと並のかなの違い1つだけか"""
    try:
        from morphology import tokenize
        lt, gt = list(tokenize(line)), list(tokenize(got))
    except Exception:
        return False
    kl = next((t.end for t in lt if t.start < i2 <= t.end), None)
    if kl is None:
        return False
    kg = kl - i2 + j2
    if kg <= 0 or line[kl:] != got[kg:] or not any(t.end == kg for t in gt):
        return False
    rl = ''.join(getattr(t, 'reading', '') or '' for t in lt if t.end <= kl)
    rg = ''.join(getattr(t, 'reading', '') or '' for t in gt if t.end <= kg)
    if not rl or not rg or len(rl) != len(rg) or rl == rg:
        return False
    diff = [k for k in range(len(rl)) if rl[k] != rg[k]]
    return len(diff) == 1 and rl[diff[0]].translate(_SMALL) == rg[diff[0]].translate(_SMALL)


def _intrusion_drop(line, got, i2, j1, j2):
    """元の行の頭から直した所の語の終わりまでの読みから、隣のキーのかなを1字抜くと直した行の読みになるか
    （も｜みと → もと: み は も の隣のキーを一緒に押した巻き込み）。"""
    try:
        from morphology import tokenize
        import kana_layout as K
        lt, gt = list(tokenize(line)), list(tokenize(got))
    except Exception:
        return False
    kl = next((t.end for t in lt if t.start < i2 <= t.end), None)
    if kl is None:
        return False
    kg = kl - i2 + j2
    if kg <= 0 or line[kl:] != got[kg:] or not any(t.end == kg for t in gt):
        return False
    hira = lambda x: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in x)
    rl = hira(''.join(getattr(t, 'reading', '') or '' for t in lt if t.end <= kl))
    rg = hira(''.join(getattr(t, 'reading', '') or '' for t in gt if t.end <= kg))
    if not rl or not rg or len(rl) != len(rg) + 1:
        return False
    for k in range(len(rl)):
        if rl[:k] + rl[k + 1:] != rg:
            continue
        if k == 0 and _natural_on():
            # 抜くのが行の頭の字そのもの（も｜水戸 → みと）なら、行の頭の字を捨てるだけで、打ち違いを戻して語にした跡ではない
            # （2026-11-21 Fable5.2 の意見: 新しい語は行の頭の字を含むこと）。CN_HEAD_ALONE_NATURAL=0 で前のまま
            continue
        for c, end in ((rl[k - 1:k], -1), (rl[k + 1:k + 2], 0)):
            try:
                if c and 0 < K.intrusion_key_distance(K.keystrokes(rl[k])[0], K.keystrokes(c)[end]) <= 1.0:
                    return True
            except Exception:
                continue
    return False


COST_GAP = 2.0


def _keyslip_rest_broken(line, got, result):
    """前の行から続きうる行でも、1キーの打ち違いの窓の直し（行の頭の の＋日 → 残）で、元の行から頭の助詞を外した
    残り（日っています）が、直した行（残っています）より解析の費用で COST_GAP 倍より高い（語の並びとして読めない）なら、
    続きの文の助詞ではなく打ち違いの跡（2026-11-17 うに: 前の行が名詞で終わると直らず、別のタブでは直った）。
    CN_HEAD_KEYSLIP_COST=0 で前のまま"""
    if os.environ.get('CN_HEAD_KEYSLIP_COST') == '0':
        return False
    head = [d for d in (result.get('details') or ()) if isinstance(d, (list, tuple)) and len(d) > 2
            and isinstance(d[0], str) and line.startswith(d[0])]
    if not head or not all(str(d[2]).startswith(KEYSLIP_REASON) for d in head):
        return False
    try:
        import morphology
        rest = morphology.path_cost(line[1:])
        new = morphology.path_cost(got)
    except Exception:
        return False
    return bool(new) and rest > COST_GAP * new


_UNKNOWN = object()


def keep_head(line, result, previous_line=_UNKNOWN):
    """result の直しのうち、行の頭の助詞を巻き込んだものを元に戻す。previous_line（1行前）を渡すと、1行前が空の行・
    文の終わりのときは戻さない（前の行から続く文ではないので、行の頭の助詞は打ち違いの跡: correction_entry.head_may_continue）"""
    if os.environ.get('CN_HEAD_PARTICLE_KEEP') == '0' or not isinstance(result, dict):
        return result
    fresh = False      # 1行前が空の行・文の終わり（前から続く文ではない）
    if previous_line is not _UNKNOWN:
        try:
            import correction_entry
            fresh = not correction_entry.head_may_continue(previous_line)
        except Exception:
            fresh = False
    got = result.get('corrected') or line
    if got == line and _head_ok(line) and os.environ.get('CN_HEAD_PARTICLE_PAIR') != '0':
        # 書き換えの無い行で、行の頭の助詞と後ろの語の組だけを理由にした紫（「を」と「発動」は続けて置けない）は、
        # 前の行から続く書き方・語句の切り出しで、打ち違いの跡ではない（1行前が空でも同じ。2026-11-16 うに: を発動した に紫）。
        # CN_HEAD_PARTICLE_PAIR=0 で前のまま
        pair = '「%s」と「' % line[0]
        drop = set()
        for x in result.get('odd_spans') or ():
            if x[0] != 0:
                continue
            why = [r[2] for r in result.get('odd_reasons') or () if len(r) >= 3 and r[0] < x[1] and x[0] < r[1]]
            if why and all(isinstance(w, str) and w.startswith(pair) and w.endswith('は続けて置けない') for w in why):
                drop.add(tuple(x[:2]))
        if drop:
            out = dict(result)
            out['odd_spans'] = [x for x in result.get('odd_spans') or () if tuple(x[:2]) not in drop]
            out['odd_reasons'] = [r for r in result.get('odd_reasons') or ()
                                  if not any(r[0] < b and a < r[1] for a, b in drop)]
            if 'unsure_spans' in result:
                out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if tuple(x[:2]) not in drop]
            return out
    if got == line or not _head_ok(line):
        return result
    ops = difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes()
    first = next((o for o in ops if o[0] != 'equal'), None)
    if first is None or first[1] != 0:
        return result
    tag, i1, i2, j1, j2 = first
    if fresh:
        # 前から続く文ではないので、行の頭の助詞は打ち違いの跡でありうる。1キーの打ち違いの窓の直し（かなの並びを打鍵で
        # 戻した直し: 行の頭の の＋語 を1字に戻す）はそのまま通す。ほかの段が助詞を後ろの語と合わせて別の語にした直し
        # （作った例: も他をうたう → モチをうたう）は確かめられないので、戻して紫にする（紫なしで通さない）
        head = [d for d in (result.get('details') or ()) if isinstance(d, (list, tuple)) and len(d) > 2
                and isinstance(d[0], str) and line.startswith(d[0])]
        if head and all(str(d[2]).startswith(KEYSLIP_REASON) for d in head):
            return result
        if os.environ.get('CN_HEAD_SMALL_TOGGLE') != '0' and _small_toggle(line, got, i2, j1, j2):
            # 行の頭の助詞と後ろの語の読みをつなぐと、小書きのかな1つ（シフトの押し忘れ: にゆう → にゅう）だけで直した語の
            # 読みになる直しは、打ち違いの跡がはっきりしているので通す（2026-11-16 うに 未解決タブ: に有力ミス）。
            # CN_HEAD_SMALL_TOGGLE=0 で前のまま
            return result
        if os.environ.get('CN_HEAD_INTRUSION_DROP') != '0' and _intrusion_drop(line, got, i2, j1, j2):
            # 行の頭の助詞と後ろの語の読みをつなぐと、隣のキーのかな1字の巻き込み（も｜みと の み）を抜くだけで直した語の
            # 読みになる直しは、打ち違いの跡がはっきりしているので通す（2026-11-16 うに: 以前は直っていた行）。
            # CN_HEAD_INTRUSION_DROP=0 で前のまま
            return result
    if not fresh and _keyslip_rest_broken(line, got, result):
        return result
    fixed = line[i1:i2] + got[j2:]
    out = dict(result)
    lops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out['corrected'] = fixed
    out['changed'] = fixed != line
    out['spans'] = [[o[3], o[4]] for o in lops]
    out['original_spans'] = [[o[1], o[2]] for o in lops]
    gone = got[j1:j2]
    out['details'] = [d for d in (result.get('details') or ())
                      if not (isinstance(d, (list, tuple)) and len(d) > 1 and d[1] == gone and d[0] == line[i1:i2])]
    # 紫は元の行の位置。戻した所（元の行の i1..i2）に掛かる紫だけ外す
    odd = [x for x in result.get('odd_spans') or () if not (x[0] < max(i2, i1 + 1) and i1 < x[1])]
    out['odd_spans'] = odd
    if fresh and os.environ.get('CN_HEAD_KEEP_PURPLE') != '0' and not _rest_reads(line, got):
        sp = (i1, max(i2, i1 + 1))
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in odd) | {sp})
        out['odd_reasons'] = [r for r in result.get('odd_reasons') or ()
                              if not (r[0] < sp[1] and sp[0] < r[1])] + [(sp[0], sp[1], REASON)]
    return out


def _natural_on():
    # 上の行を見ない形（CN_PREV_LINE_OFF・2026-11-21）の時だけ。CN_HEAD_ALONE_NATURAL=0 で前のまま
    return os.environ.get('CN_HEAD_ALONE_NATURAL') != '0' and os.environ.get('CN_PREV_LINE_OFF') != '0'


def _rest_reads(line, got):
    """行の頭の助詞を外した残り（後ろから抱きついた）が、直した行（の候補）より解析の費用で高くない（ふつうに読める）か。
    読めるなら、行の頭の1字は前から続く文の助詞として置いたもので、元に戻すだけにして紫を付けない（2026-11-21 うに:
    行の頭の助詞もその行だけで直す。ただし 助詞＋身近な語 がふつうに読める行は崩さない）。CN_HEAD_ALONE_NATURAL=0 で前のまま"""
    if not _natural_on():
        return False
    try:
        import morphology
        rest = morphology.path_cost(line[1:])
        new = morphology.path_cost(got)
    except Exception:
        return False
    return bool(rest) and bool(new) and rest <= new


def _previous_line(line, a, k):
    # 外の行の補正の中で回す補正し直し（候補を通す）は、外の行の1行前のまま見る
    try:
        import correction_entry
        v = correction_entry._PREV_LINE.get()
        if v is not correction_entry._PREV_UNKNOWN:
            return v
    except Exception:
        pass
    try:
        import inspect
        return inspect.signature(_orig['correct_line']).bind(line, *a, **k).arguments.get('previous_line')
    except Exception:
        return _UNKNOWN


def correct_line(line, *a, **k):
    return keep_head(line, _orig['correct_line'](line, *a, **k), _previous_line(line, a, k))


def install():
    if _orig or os.environ.get('CN_HEAD_PARTICLE_KEEP') == '0':
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    # 包みの外から元の引数（defer_heavy・tab_has_kana など）が見えるように（analysis_worker が inspect.signature で見る・2026-11-13）
    import functools
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True


def uninstall():
    if not _orig:
        return
    import correction_entry
    correction_entry.correct_line = _orig.pop('correct_line')
