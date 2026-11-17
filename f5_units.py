# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""F5（候補一覧）で渡り歩く語の単位の手直し（2026-11-16 うにさん「F5の範囲選択で遡ると、単語の前のをが単語に付いてきた」）。

ひらがなの続く所では、形態素の切り方が助詞「を」を隣の語に付けてしまうことがある（作った例: 「みずをかう。」が
み｜ずを｜かう と切れ、かう から遡ると「ずを」が選ばれた）。「を」は今の日本語では語の中に現れない（助詞だけ）ので、
単位の頭か尻にある「を」を、助詞の単位として切り離す。F5 は助詞を飛ばして渡り歩くので、「を」は選ばれなくなる。
が・に・は などは語の中にもある（かがみ・にわ・はな）ので切らない。補正の提案（detail）を持つ単位は触らない
（その単位の範囲で直しが決まっている）。切り離した「を」には f5_skip を付け、F5 の渡り歩きはいつも飛ばす
（その所では「を」にも候補が出ることがあり、候補が出るかで決める飛ばし方では止まった）。CN_F5_WO_SPLIT=0 で前の単位のまま。
"""
import os

PARTICLE = 'を'


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_WO_SPLIT') != '0'


def _piece(unit, start, end, text, particle):
    piece = dict(unit)
    piece.update(start=start, end=end, text=text)
    if particle:
        piece.update(base=PARTICLE, reading=PARTICLE, pos='助詞:格助詞:一般', infl='', kind='plain', detail=None,
                     atomic=True, functional=True, known=True, f5_skip=True)
    else:
        for key in ('base', 'reading'):
            value = unit.get(key)
            if isinstance(value, str) and value == unit.get('text'):
                piece[key] = text
    return piece


def split_wo(units, environ=None):
    """単位の並びの、頭か尻に「を」がある単位（提案なし・2字以上）を、語と「を」に分けた新しい並び。
    分けない単位は同じ dict のまま（F5 の `is` の比べがそのまま効く）。"""
    if not enabled(environ) or not units:
        return units
    out = []
    changed = False
    for unit in units:
        text = unit.get('text') or ''
        start, end = unit.get('start'), unit.get('end')
        if (len(text) < 2 or unit.get('detail') or start is None or end is None or end - start != len(text)
                or PARTICLE not in (text[0], text[-1]) or text == PARTICLE * len(text)):
            out.append(unit)
            continue
        changed = True
        if text[-1] == PARTICLE:
            out.append(_piece(unit, start, end - 1, text[:-1], False))
            out.append(_piece(unit, end - 1, end, PARTICLE, True))
        else:
            out.append(_piece(unit, start, start + 1, PARTICLE, True))
            out.append(_piece(unit, start + 1, end, text[1:], False))
    if not changed:
        return units
    # 前後の字（prev・next）も、切り離した後の隣に合わせる（分けた単位だけ。分けない単位の dict は替えない）
    for k, unit in enumerate(out):
        if unit.get('text') == PARTICLE or (k + 1 < len(out) and out[k + 1].get('text') == PARTICLE) or                 (k > 0 and out[k - 1].get('text') == PARTICLE):
            if unit not in units or unit.get('text') == PARTICLE:
                unit['prev'] = out[k - 1].get('text', '') if k > 0 else unit.get('prev', '')
                unit['next'] = out[k + 1].get('text', '') if k + 1 < len(out) else unit.get('next', '')
    return out
