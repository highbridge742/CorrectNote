# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""紫の残る語を、同じ読みの別の表記に替えて通し直し、紫が消えて書き換えも出ない形が1つだけなら採る
（2026-11-14 補正担当・全体評価の案「紫の範囲の語だけ同じ読みの候補を聞く」）。

なぜ
----
同じ読みの選び違い（作った例: 続きを離す → 話す、作業を官僚にする → 完了）は、どちらもよく使う語なので
ime_reconvert の珍しさの門（DOUBT）で候補を作る前に止まり、別の段が紫だけを付けて残る。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（functools.update_wrapper あり）。
1. 書き換えが無く紫だけが残る行だけを見る（紫の無い行・書き換えの在る行は何もしない）。紫の範囲（答えの行の位置）に重なる語のうち、漢字を含み、
   2字以上で読みの在る自立語（名詞・動詞・形容詞）を（1字の漢字は崩れた打ち方の切れ端のことが多い: 紙→上 にしない）、紫の範囲ごとに1語ずつ選ぶ。
2. その語の読み（解析の読み）で辞書（reading_lattice の表）を引き、同じ品詞で漢字を含み、身近な（ime_reconvert._rank が
   COMMON 以下の）別の表記を候補にする。紫がその語の中に収まる所だけ見る。IME は聞かない（雲と PC で同じ答えになる）。
3. 候補に替えた行を元の correct_line でもう一度通し、書き換えも紫も出ない候補だけを残す。
4. 通る候補がちょうど1つなら採る（書き換え・details を足し、その紫を外す）。0 か2つ以上なら今のまま紫。
紫の全部が選んだ語の中に収まる行だけ、理由が「あまり使わない語です」だけの紫が在る行は見ない。通し直しは1行に MAX_TRIES 回まで。特定の語や文字列には合わせない。
切り替え: 既定はオン（2026-11-14 うにのカード「オンにする」）。CN_PURPLE_HOMOPHONE=0 で前のまま。
"""
import difflib
import functools
import os

COMMON = 530
MAX_SPANS = 2
MAX_TRIES = 6
_POS = ('名詞', '動詞', '形容詞')
_orig = {}
_busy = []


def _on():
    return os.environ.get('CN_PURPLE_HOMOPHONE') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (s or ''))


def _candidates(tok):
    try:
        import reading_lattice as lat
        import ime_reconvert as R
        lat.load()
        rd = _hira(tok.reading)
        out = []
        for f, _l, _r, _c, p in lat._table.get(rd, ()):
            if (p == tok.pos and f != tok.surface and f not in out and any(_kanji(c) for c in f)
                    and R._rank(f) <= COMMON):
                out.append(f)
        return out
    except Exception:
        return []


def _targets(text, spans):
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return []
    picked = []
    for a, b in spans[:MAX_SPANS]:
        hit = [t for t in toks if t.start < b and a < t.end and t.pos in _POS
               and not str(t.pos_sub or '').startswith(('非自立', '接尾', '固有名詞', '数'))
               and len(t.surface) >= 2 and any(_kanji(c) for c in t.surface) and t.reading and t.reading != '*']
        # 紫がその語の中に収まる所だけ（紫が助詞や隣の語まで掛かる所は、打ち違いが語の外にも在る: 準備が鳴かな）
        if len(hit) == 1 and hit[0].start <= a and b <= hit[0].end and hit[0] not in picked:
            picked.append(hit[0])
    return picked


def _chosen_rare(tok):
    """打った語がとても珍しい（ime_reconvert._rank が DOUBT_KEY 以上）なら、書き手が候補を下って選んだ表記とみて替えない。
    同じ読みの身近な語が IME の最初の候補に出るので、珍しい方は選ばなければ出ない（2026-11-17 うに 誤判定:
    先年の → 専念の）。切り替え CN_PURPLE_HOMOPHONE_RARE_KEEP=0 で前のまま"""
    if os.environ.get('CN_PURPLE_HOMOPHONE_RARE_KEEP') == '0':
        return False
    try:
        import ime_reconvert as R
        return R._rank(tok.surface) >= R.DOUBT_KEY
    except Exception:
        return False


RANK_GAP = 40   # 替える表記が打った語よりこれだけ身近（段が小さい）でなければ替えない


def _near_rank(src, face):
    """替える表記の身近さが打った語と変わらない（段の差が RANK_GAP 未満: 発送 488・発想 476）なら替えない。IME は同じ読みの
    身近な方を先に出すので、身近さの並ぶ語を選んだのは書き手（2026-11-20 正しい文の見直し: 賞品の発送 → 発想）。
    切り替え CN_PURPLE_HOMOPHONE_NEAR_RANK=0 で前のまま"""
    if os.environ.get('CN_PURPLE_HOMOPHONE_NEAR_RANK') == '0':
        return False
    try:
        import ime_reconvert as R
        return R._rank(src) - R._rank(face) < RANK_GAP
    except Exception:
        return False


def _na_before_suru(text, tok, face):
    """替える表記 face が形容動詞の語幹（好調・綺麗）で、打った語のすぐ後ろが する の活用（し・す・さ・せ）なら替えない。
    形容動詞の語幹に する は付かない（好調した とは言わない）ので、紫が消えても文の形にならない
    （2026-11-20 正しい文の見直し: 顔が高潮した → 好調した）。打った語も形容動詞の語幹なら見ない。
    切り替え CN_PURPLE_HOMOPHONE_NA_SURU=0 で前のまま"""
    if os.environ.get('CN_PURPLE_HOMOPHONE_NA_SURU') == '0':
        return False
    try:
        from morphology import tokenize
        nxt = [t for t in tokenize(text) if t.start == tok.end]
        if not nxt or nxt[0].pos != '動詞' or nxt[0].base_form != 'する':
            return False
        if str(tok.pos_sub or '') == '形容動詞語幹':
            return False
        ft = list(tokenize(face))
        return len(ft) == 1 and str(ft[0].pos_sub or '') == '形容動詞語幹'
    except Exception:
        return False


def _clean(res, new):
    return (isinstance(res, dict) and (res.get('corrected') or new) == new
            and not res.get('odd_spans') and not res.get('unsure_spans'))


def respell(line, result, run):
    """result の紫を同じ読みの表記で消せるなら、消した答え。run(新しい行) は元の correct_line を通す関数"""
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    if not odd:
        return result
    text = result.get('corrected') or line
    if text != line:
        return result          # 紫は元の行の位置なので、書き換えの無い行（紫だけの行）だけを見る
    # 珍しいというだけの紫（あまり使わない語です）は、書き手が選んだ表記を身近な同音の語に替える根拠にならない
    # （作った例: 貴社 を 記者 にしない）。その理由だけの紫が1つでも在る行は見ない
    why = {}
    for r in result.get('odd_reasons') or ():
        if len(r) >= 3:
            why.setdefault((r[0], r[1]), []).append(str(r[2]))
    if any(all('あまり使わない語です' in t for t in why.get(sp, ['あまり使わない語です'])) for sp in odd):
        return result
    targets = _targets(text, odd)
    # 紫の全部が選んだ語の中に収まる行だけ（紫が2か所あって1か所だけ替えると、通し直しは紫なしでも残りの紫と食い違う）
    if not targets or not all(any(t.start <= a and b <= t.end for t in targets) for a, b in odd):
        return result
    tries = 0
    out = result
    for tok in targets:
        if _chosen_rare(tok):
            continue
        ok = []
        for f in _candidates(tok):
            if tries >= MAX_TRIES:
                break
            if _na_before_suru(text, tok, f):
                continue
            tries += 1
            new = text[:tok.start] + f + text[tok.end:]
            try:
                res = run(new)
            except Exception:
                continue
            if _clean(res, new):
                ok.append(f)
        if len(ok) == 1 and _variant(tok, ok[0]):
            out = _drop_purple(out, tok)
            continue
        if len(ok) != 1 or _near_rank(tok.surface, ok[0]):
            continue
        f = ok[0]
        text = text[:tok.start] + f + text[tok.end:]
        out = _rebuild(line, out, text, tok, f)
    return out


def _variant(tok, face):
    """face が打った語 tok の別の書き方（奇麗・綺麗: 同じ読みの同じ品詞で、漢字を共に持つ）か。別の書き方に替えると
    紫は消えるが、書き手の選んだ表記を替える理由にならない。そのときは表記を替えず、その語の紫を外す（2026-11-20
    正しい文の見直し: 奇麗ではありません → 綺麗）。CN_PURPLE_HOMOPHONE_VARIANT=0 で前のまま"""
    if os.environ.get('CN_PURPLE_HOMOPHONE_VARIANT') == '0':
        return False
    kanji = lambda c: '\u4e00' <= c <= '\u9fff'
    if not (set(c for c in tok.surface if kanji(c)) & set(c for c in face if kanji(c))):
        return False
    try:
        from morphology import tokenize
        ft = list(tokenize(face))
    except Exception:
        return False
    return (len(ft) == 1 and ft[0].pos == tok.pos and ft[0].pos_sub == tok.pos_sub
            and ft[0].reading == tok.reading and len(face) == len(tok.surface))


def _drop_purple(result, tok):
    out = dict(result)
    inside = lambda x: tok.start <= x[0] and x[1] <= tok.end
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if not inside(x)]
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or () if not (len(r) >= 2 and inside(r))]
    return out


def _rebuild(line, result, text, tok, face):
    out = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
    shift = len(face) - (tok.end - tok.start)

    def keep(x):
        return not (x[0] < tok.end and tok.start < x[1])

    def move(x):
        if x[0] < tok.end:
            return x
        y = list(x)
        y[0] += shift
        y[1] += shift
        return tuple(y) if isinstance(x, tuple) else y
    out['odd_spans'] = [move(x) for x in result.get('odd_spans') or () if keep(x)]
    out['odd_reasons'] = [move(x) for x in result.get('odd_reasons') or () if keep(x)]
    out.update({'corrected': text, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops]})
    out['details'] = list(result.get('details') or ()) + [(tok.surface, face, '同じ読みの別の表記で紫が消える')]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    if not _on() or _busy:
        return result
    _busy.append(1)
    try:
        return respell(line, result, lambda new: _orig['correct_line'](new, *args, **kwargs))
    except Exception:
        return result
    finally:
        _busy.pop()


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
