# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
動詞の連用形に、て で受けるはずの補助の動詞（しまう・おく・みる・いる・いく・くる・もらう・くれる など）が
て を挟まずに続く所を、て の脱字として戻す段（te_dropped・2026-11-01・手分け C の自走）。

  - 一段の動詞（連用形＝基本形の る を取った形）・する（し）・来る（来）・す で終わる五段（連用形 し、て形は して）は、
    連用形の後ろに て を1字足すと て形になる。足す字が1つに決まるので直す（脱字の戻し）。
  - ほかの五段（音便で て形が変わる）は1字足すだけでは戻らない。紫にする（決めるか紫・うに 10-18）。
  - 辞書に1語の複合動詞として在る並び（書き置く 等）は見ない。
また、動詞の連用形に する の連用形（し）＋た・て が直に続く所（変わり＋し＋た）は、ました・まして の ま の脱字として
ま を足す（動詞の連用形に する は付かない。連用形が名詞になった語は名詞として切られる: 買い物した）。
品詞と活用の形だけで見る。特定の語や文字列には合わせない。
"""
import os
import difflib

_TE_AUX = frozenset(('しまう', 'おく', 'みる', 'いる', 'おる', 'ある', 'いく', 'くる', 'もらう', 'くれる',
                     'いただく', 'くださる'))
# 連用形に直に付いて複合の動詞にもなる補助の動詞（書きおく・持ちあげる は正しい形）。五段の連用形の後ろでは見ない
_COMPOUNDABLE = frozenset(('おく', 'あげる', 'いる', 'おる'))


def _te_insertable(t):
    base = t.base_form or ''
    if t.surface == 'し' and base == 'する':
        return True
    if base in ('来る', 'くる') and t.surface in ('来', 'き'):
        return True
    if base.endswith('る') and t.surface == base[:-1] and t.surface:
        return True     # 一段
    if base.endswith('す') and t.surface == base[:-1] + 'し':
        return True     # す で終わる五段（話し → 話して）
    return False


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (s or ''))


def _joined_word(a, b):
    try:
        import reading_lattice
        reading_lattice.load()
        rd = _hira(a.reading or a.surface) + _hira(b.base_form or '')
        return bool(reading_lattice._table.get(rd))
    except Exception:
        return False


def _one_kanji_stem(t):
    s = t.surface or ''
    return len(s) == 1 and ('\u4e00' <= s <= '\u9fff')


def propose(text):
    """[(位置, 'て' か None)] 位置は連用形の終わり。None は紫だけ（範囲は連用形の語と補助の動詞）。"""
    from morphology import tokenize, dictionary_inflections
    toks = list(tokenize(text))
    out = []
    for i in range(len(toks) - 2):
        a, b, c = toks[i], toks[i + 1], toks[i + 2]
        if (a.end == b.start and a.pos == '動詞' and (a.pos_sub or '') == '自立' and a.infl_form == '連用形'
                and (a.base_form or '') not in ('する', '為る') and b.surface == 'し' and (b.base_form or '') == 'する'
                and b.start == c.start - 1 and c.surface in ('た', 'て')):
            # 語幹が漢字1字だけの動詞（見・寝・出 など）は別の動詞の打ち違い（見せて 等）とも読めるので決めずに紫
            # 3字以上の連用形（逆立ち・後ずさり）は名詞として する が付く正しい形が多いので見ない（例文 Tatoeba の
            # 正しい文で 逆立ちして→逆立ちまして にしていた・2026-11-07）。CN_TE_LONG_STEM=0 で前のまま
            if len(a.surface) >= 3 and os.environ.get('CN_TE_LONG_STEM') != '0':
                continue
            # お・ご＋連用形＋する（お会いした・お待ちしています）は謙譲の正しい形（2026-11-07 例文 Tatoeba）。CN_TE_O_SURU=0
            if (i and toks[i - 1].end == a.start and toks[i - 1].surface in ('お', 'ご', '御')
                    and os.environ.get('CN_TE_O_SURU') != '0'):
                continue
            out.append((a.start, a.end, c.end, None if _one_kanji_stem(a) else 'ま'))
    for i in range(len(toks) - 1):
        a, b = toks[i], toks[i + 1]
        if a.end != b.start or a.pos != '動詞' or (a.pos_sub or '') != '自立' or a.infl_form != '連用形':
            continue
        if b.pos != '動詞' or not (b.pos_sub or '').startswith('非自立') or (b.base_form or '') not in _TE_AUX:
            continue
        try:
            comp = dictionary_inflections(a.surface + b.surface)
        except Exception:
            comp = None
        if comp and any(str(p).startswith('動詞,') for p, *_r in comp):
            continue
        # 読みの表に1語として在る並び（みいる＝見入る）も複合の動詞として見ない
        if _joined_word(a, b):
            continue
        # お・ご＋連用形＋ください（お取りください・お締めください）は敬語の正しい形（例文 Tatoeba の正しい文で紫が
        # 付いていた・2026-11-07）。CN_TE_O_KUDASAI=0 で前のまま
        if ((b.base_form or '') in ('くださる', '下さる') and i and toks[i - 1].end == a.start
                and toks[i - 1].surface in ('お', 'ご', '御') and os.environ.get('CN_TE_O_KUDASAI') != '0'):
            continue
        ins = _te_insertable(a)
        if not ins and (b.base_form or '') in _COMPOUNDABLE:
            continue
        # 連用形の語が助詞の後ろ（を忘れ・が変わり）か行頭・句読点の後ろに立つときだけ て を足す。名詞やお・ご、別の動詞に
        # 直に付く連用形（間違い掛け・ご確認き・お当て・置いてくだし）は1打違いが動詞に化けた形のことが多く、足しても
        # 直らない（新しい試験の隣キー1,500件で て を足した8件がどれも誤り・2026-11-02）。決めずに紫
        prev = toks[i - 1] if i and toks[i - 1].end == a.start else None
        anchored = prev is None or prev.pos == '記号' or (
            prev.pos == '助詞' and not (prev.pos_sub or '').startswith('接続助詞'))
        # 補助の動詞が言い切られずに漢字へ続く形（遅れい申し訳）も同じ
        tail = text[b.end:b.end + 1]
        nxt = toks[i + 2] if i + 2 < len(toks) and toks[i + 2].start == b.end else None
        broken = b.infl_form == '連用形' and len(b.surface) == 1 and not (
            'ぁ' <= tail <= 'ゖ' and nxt is not None and (nxt.pos == '助動詞' or (nxt.pos_sub or '').startswith('接続助詞')))
        out.append((a.start, a.end, b.end, 'て' if ins and anchored and not broken and not _one_kanji_stem(a) else None))
    return out


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        found = propose(done)
    except Exception:
        return result
    if not found:
        return result
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    details, odd_add, cleared = [], [], []
    for s, at, e, rep in sorted(found, reverse=True):
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None:
            # 前の段が直した所に掛かるなら、紫は付けられない（位置が元の行に無い）。直すだけ見る
            if rep is None:
                continue
        elif any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        elif rep is None and any(x < org[1] and org[0] < y for x, y in odd_now):
            continue
        elif rep and org is not None:
            cleared.append(org)
        if rep:
            new = new[:at] + rep + new[at:]
            details.append([done[s:e], new[s:e + 1], '脱字（' + rep + '）'])
        else:
            odd_add.append(org)
    if new == done and not odd_add:
        return result
    out = dict(result)
    if cleared:
        # 足す字が1つに決まって直した所の紫・迷い（前の段が付けた）は外す
        for key in ('odd_spans', 'unsure_spans'):
            if result.get(key):
                out[key] = [sp for sp in result[key] if not any(x < sp[1] and sp[0] < y for x, y in cleared)]
    if odd_add:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, '動詞のあとに て・ま が抜けているかもしれません') for a, b in odd_add]
        # 打ち違いの戻し（odd_respell）は当てない（1打の戻しで別の語の複合動詞にしてしまう）
        out['face_doubt_spans'] = list(result.get('face_doubt_spans') or ()) + list(odd_add)
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
